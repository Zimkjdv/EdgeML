from __future__ import annotations

import json
import logging
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5
import hashlib
import os
from functools import wraps
from threading import Lock
from weakref import WeakValueDictionary

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    AdaBoostClassifier,
    AdaBoostRegressor,
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, OneHotEncoder
from sklearn.decomposition import TruncatedSVD
from sklearn.base import BaseEstimator, ClassifierMixin, clone
from xgboost import XGBClassifier, XGBRegressor

from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.domain.model_catalog import ModelRegistry
from app.domain.schemas import ModelManifest
from app.domain.training_schemas import TrainedModelDetail, TrainedModelSummary, TrainingRequest
from app.domain.training_schemas import ExternalEvaluationResult, TestEvaluationContext, TrainingJob
from app.core.observability import training_finished, training_started
from app.services.dataset_service import DatasetService
from app.services.regression_metrics import regression_metrics
from app.services.feature_importance_service import ImportanceUnavailable, calculate_importance, read_importance, save_importance
from app.core.config import get_settings
from app.infrastructure.file_lock import FileLock, child_path
from app.services.training_data import clean_supervised_frame
from app.services.validation_strategy import validation_splits
from app.services.cross_validation import evaluate_folds
from app.services.prediction_csv import read_prediction_csv
from app.infrastructure.atomic_json import write_json_atomic


def job_state_transaction(method):
    @wraps(method)
    def locked(self, job_id, *args, **kwargs):
        with self._job_state_lock(job_id):
            return method(self, job_id, *args, **kwargs)
    return locked


def job_execution(method):
    @wraps(method)
    def locked(self, job_id, *args, **kwargs):
        path = child_path(self._jobs_root / '.execution-locks', f'{job_id}.lock')
        with FileLock(path, timeout=0):
            return method(self, job_id, *args, **kwargs)
    return locked


class EncodedTargetClassifier(ClassifierMixin, BaseEstimator):
    """Keep string classification labels compatible with XGBoost's numeric target requirement."""

    def __init__(self, pipeline: Pipeline) -> None:
        self.pipeline = pipeline

    def fit(self, features, target):
        self.encoder_ = LabelEncoder().fit(target)
        self.pipeline_ = clone(self.pipeline)
        self.pipeline_.fit(features, self.encoder_.transform(target))
        self.classes_ = self.encoder_.classes_
        return self

    def predict(self, features):
        encoded = self.pipeline_.predict(features)
        return self.encoder_.inverse_transform(np.asarray(encoded, dtype=int))

    def predict_proba(self, features):
        return self.pipeline_.predict_proba(features)


class TrainingService:
    def __init__(self, datasets: DatasetService, trained_models_root: Path, publish_root: Path, jobs_root: Path | None = None, model_registry: ModelRegistry | None = None) -> None:
        self._datasets = datasets
        self._trained_root = trained_models_root
        self._publish_root = publish_root
        self._trained_root.mkdir(parents=True, exist_ok=True)
        self._publish_root.mkdir(parents=True, exist_ok=True)
        self._jobs_root = jobs_root or trained_models_root.parent / "training_jobs"
        self._jobs_root.mkdir(parents=True, exist_ok=True)
        self._model_registry = model_registry
        self._logger = logging.getLogger("edgeml.training")
        self._state_locks = WeakValueDictionary()
        self._model_locks = WeakValueDictionary()
        self._state_locks_guard = Lock()

    def train(self, request: TrainingRequest, progress=None, *, model_id: str | None = None,
              job_id: str | None = None) -> TrainedModelDetail:
        model_id = model_id or str(uuid4())
        with self._model_lock(model_id):
            return self._train_model(request, progress, model_id, job_id)

    def _train_model(self, request, progress, model_id, job_id):
        if child_path(self._trained_root, model_id).exists():
            raise PredictionValidationError('Output model already exists; refusing to overwrite it.')
        if progress: progress(10, "驗證資料與訓練設定")
        frame = self._datasets.frame(request.dataset_id)
        frame = clean_supervised_frame(frame, request.feature_columns, request.target_column, request.numeric_imputer)
        self._validate_request(frame, request)
        frame, cv = validation_splits(frame, request)
        features = frame[request.feature_columns]
        target = frame[request.target_column] if request.problem_type == "classification" else pd.to_numeric(frame[request.target_column], errors="raise")
        pipeline = self._pipeline(features, request)
        if progress: progress(25, "進行交叉驗證")
        fold_result = evaluate_folds(pipeline, features, target, cv, request.problem_type == "classification",
            (lambda completed, total: progress(25 + int(40 * completed / total), f"交叉驗證 {completed}/{total} 折完成")) if progress else None)
        evaluated = fold_result.indices
        evaluated_target = target.iloc[evaluated]
        validation = (self._classification_metrics(evaluated_target, fold_result.predictions, fold_result.scores, fold_result.probabilities)
                      if request.problem_type == "classification" else
                      self._regression_metrics(evaluated_target, fold_result.predictions, fold_result.scores))
        if progress: progress(70, "以完整資料集訓練模型")
        pipeline.fit(features, target)
        if progress: progress(85, "儲存模型 artifact")
        validation_rmse = validation.get("rmse")
        validation_r2 = validation.get("r2")
        test_metrics = self._external_test(pipeline, request) if request.test_dataset_id else None
        if progress: progress(90, "計算特徵重要度")
        importance_frame = self._datasets.frame(request.test_dataset_id) if request.test_dataset_id else frame
        importance_frame = clean_supervised_frame(importance_frame, request.feature_columns, request.target_column, request.numeric_imputer)
        importance = calculate_importance(pipeline.predict, importance_frame[request.feature_columns],
                                         importance_frame[request.target_column], request.problem_type == 'classification',
                                         request.test_dataset_id or request.dataset_id,
                                         'external_test' if request.test_dataset_id else 'training',
                                         get_settings().importance_max_samples, get_settings().importance_repeats)
        completed_at = datetime.now(timezone.utc)
        manifest = self._manifest(model_id, request, completed_at, validation, test_metrics, features)
        from app.domain.feature_defaults import summarize_features
        manifest['training_dataset_id'] = request.dataset_id
        manifest['feature_defaults'] = summarize_features(features)
        record = {
            "id": model_id,
            "name": request.model_name,
            "completed_at": completed_at.isoformat(),
            "target_column": request.target_column,
            "algorithm": request.algorithm,
            "problem_type": request.problem_type,
            "validation_rmse": validation_rmse,
            "validation_r2": validation_r2,
            "test_rmse": test_metrics.get("rmse") if test_metrics else None,
            "test_r2": test_metrics.get("r2") if test_metrics else None,
            "status": "draft",
            "feature_columns": request.feature_columns,
            "validation_metrics": validation,
            "test_metrics": test_metrics,
            "settings": request.model_dump(),
            "evaluation_version": "oof-v2",
            "validation_context": {"strategy": request.validation_strategy, "column": request.validation_column,
                "time_gap": request.time_gap, "total_rows": len(frame), "evaluated_rows": len(evaluated),
                "excluded_rows": len(frame) - len(evaluated)},
            "manifest": manifest,
        }
        self._commit_model(model_id, job_id, request, pipeline, importance, manifest, record)
        result = TrainedModelDetail.model_validate(record)
        if progress: progress(100, "訓練完成")
        return result

    @staticmethod
    def _request_digest(request):
        payload = json.dumps(request.model_dump(mode='json'), sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _artifact_digest(path):
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''): digest.update(chunk)
        return digest.hexdigest()

    def _commit_model(self, model_id, job_id, request, pipeline, importance, manifest, record):
        stage = Path(tempfile.mkdtemp(prefix=f'.staging-{model_id}-', dir=self._trained_root))
        # This directory was created by this attempt and checked inside the root.
        stage = child_path(self._trained_root, stage.name)
        destination = child_path(self._trained_root, model_id)
        try:
            write_json_atomic(stage / 'owner.json', {'job_id': job_id, 'request_sha256': self._request_digest(request)})
            save_importance(stage, importance)
            with (stage / 'model.pkl').open('wb') as stream:
                joblib.dump(pipeline, stream)
                stream.flush(); os.fsync(stream.fileno())
            write_json_atomic(stage / 'metadata.json', manifest)
            (stage / 'README.md').write_text(f'# {request.model_name}\n\nTrained by EdgeML.\n', encoding='utf-8')
            record['output_commit'] = {'job_id': job_id, 'request_sha256': self._request_digest(request),
                                       'artifact_sha256': self._artifact_digest(stage / 'model.pkl')}
            write_json_atomic(stage / 'record.json', record)
            if destination.exists():
                raise PredictionValidationError('Output destination already exists.')
            stage.rename(destination)
        finally:
            if stage.exists():
                shutil.rmtree(child_path(self._trained_root, stage.name))

    def _recover_output(self, job, request):
        destination = child_path(self._trained_root, job.output_model_id)
        if not destination.exists(): return None
        if not all((destination / name).is_file() for name in ('record.json', 'metadata.json', 'model.pkl')):
            raise PredictionValidationError('Committed output is incomplete; restore it before retrying.')
        payload = self._read_record(destination)
        commit = payload.get('output_commit', {})
        if (commit.get('job_id') != job.id or commit.get('request_sha256') != self._request_digest(request)
                or commit.get('artifact_sha256') != self._artifact_digest(destination / 'model.pkl')):
            raise PredictionValidationError('Existing output ownership/configuration/artifact verification failed.')
        ModelManifest.model_validate({**payload['manifest'], 'model_path': destination})
        if not (destination / 'metadata.json').is_file():
            raise PredictionValidationError('Committed output metadata is missing.')
        return TrainedModelDetail.model_validate(payload)

    def _archive_incomplete_staging(self, job, request):
        for stage in self._trained_root.glob(f'.staging-{job.output_model_id}-*'):
            stage = child_path(self._trained_root, stage.name)
            owner_path = stage / 'owner.json'
            owner = json.loads(owner_path.read_text(encoding='utf-8')) if owner_path.exists() else None
            if owner is not None and owner != {'job_id': job.id, 'request_sha256': self._request_digest(request)}:
                raise PredictionValidationError('Staging ownership verification failed.')
            archive = child_path(self._trained_root, f'.abandoned-{job.output_model_id}-{uuid4().hex}')
            stage.rename(archive)  # Preserve incomplete diagnostic files; never publish them.

    def create_job(self, request: TrainingRequest) -> TrainingJob:
        job = TrainingJob(id=str(uuid4()), status="queued", progress=0, message="等待訓練開始")
        job.queued_at = datetime.now(timezone.utc)
        with self._job_state_lock(job.id):
            write_json_atomic(self._dispatch_marker(job.id), {'job_id': job.id})
            self._write_job(job, request)
        return job

    def _dispatch_marker(self, job_id: str) -> Path:
        return child_path(self._jobs_root, f'.dispatch-{job_id}.txn')

    def confirm_dispatch(self, job_id: str) -> None:
        self._dispatch_marker(job_id).unlink(missing_ok=True)

    @job_state_transaction
    def note_dispatch_failure(self, job_id: str, error: str) -> TrainingJob:
        job, request = self._read_job(job_id)
        if job.status == 'queued':
            job.message = '工作已保存，等待 Redis 連線恢復後派送'
            job.error = error
            self._write_job(job, request)
        return job

    def recover_pending_dispatch(self, queue, include_confirmed: bool = False) -> None:
        ids = {marker.name[len('.dispatch-'):-4] for marker in self._jobs_root.glob('.dispatch-*.txn')}
        if include_confirmed:
            ids.update(path.stem for path in self._jobs_root.glob('*.json'))
        for job_id in ids:
            def eligible():
                try: return self.get_job(job_id).status in ({'queued', 'running'} if include_confirmed else {'queued'})
                except ModelNotFoundError: return False
            queue.ensure_enqueued(job_id, eligible)
            self.confirm_dispatch(job_id)

    @job_state_transaction
    def mark_job_failed(self, job_id: str, error: str) -> TrainingJob:
        job, request = self._read_job(job_id)
        if job.status != 'queued':
            return job  # A lost enqueue reply must not overwrite an active worker.
        job.status = "failed"
        job.message = "Training job could not be queued"
        job.error = error
        job.completed_at = datetime.now(timezone.utc)
        self._write_job(job, request)
        self.confirm_dispatch(job_id)
        return job

    @job_state_transaction
    def _begin_job(self, job_id: str, worker_id: str | None = None):
        job, request = self._read_job(job_id)
        # A recovered processing-list entry may still be persisted as running after
        # a worker crash, so it is safe to resume both queued and running jobs.
        if job.status not in {"queued", "running"}:
            raise PredictionValidationError(f"Training job '{job_id}' is not available to run.")
        job.attempt += 1
        job.output_model_id = job.output_model_id or str(uuid5(NAMESPACE_URL, 'edgeml:training-job/' + job.id))
        job.replay_pending = False
        job.error = None
        job.started_at = datetime.now(timezone.utc)
        job.worker_id = worker_id
        job.status, job.progress, job.message = "running", 2, "準備訓練環境"
        self._write_job(job, request)
        return job, request

    @job_execution
    def run_job(self, job_id: str, worker_id: str | None = None) -> TrainingJob:
        job, request = self._read_job(job_id)
        if job.status == 'completed': return job
        if job.status not in {'queued', 'running'}:
            raise PredictionValidationError('Training job is not available to run.')
        job.output_model_id = job.output_model_id or str(uuid5(NAMESPACE_URL, 'edgeml:training-job/' + job.id))
        with self._model_lock(job.output_model_id):
            try:
                result = self._recover_output(job, request)
            except (PredictionValidationError, ModelNotFoundError, ValueError) as exc:
                with self._job_state_lock(job.id):
                    current, saved = self._read_job(job.id)
                    if current.status != 'cancelled':
                        current.status, current.error = 'failed', str(exc)
                        current.message, current.completed_at = '模型成果驗證失敗', datetime.now(timezone.utc)
                        self._write_job(current, saved)
                raise
            if result is not None:
                return self._complete_job(job, request, result, worker_id)
            job, request = self._begin_job(job_id, worker_id)
            return self._run_job_output(job, request, worker_id)

    def has_committed_output(self, job_id: str) -> bool:
        try:
            job, request = self._read_job(job_id)
            if not job.output_model_id: return False
            with self._model_lock(job.output_model_id):
                return self._recover_output(job, request) is not None
        except (ModelNotFoundError, PredictionValidationError, OSError, ValueError):
            return False

    def _complete_job(self, job, request, result, worker_id):
        with self._job_state_lock(job.id):
            current, request = self._read_job(job.id)
            if current.status in {'completed', 'cancelled'}: return current
            if current.attempt != job.attempt:
                raise PredictionValidationError('A newer job attempt owns this output.')
            current.status, current.progress, current.message = 'completed', 100, '訓練完成'
            current.output_model_id = current.result_model_id = result.id
            current.worker_id = worker_id or current.worker_id
            current.completed_at, current.error = datetime.now(timezone.utc), None
            self._write_job(current, request)
            return current

    def _run_job_output(self, job, request, worker_id):
        job_id = job.id
        started_at = training_started()
        self._logger.info("Training job started", extra={"event": "training.job.started", "job_id": job_id, "worker_id": worker_id})
        try:
            result = self._recover_output(job, request)
            if result is None:
                self._archive_incomplete_staging(job, request)
                result = self.train(request, lambda progress, message: self._update_job(job, request, progress, message),
                                    model_id=job.output_model_id, job_id=job.id)
        except Exception as exc:
            self._logger.exception("Training job failed", extra={"event": "training.job.failed", "job_id": job_id, "worker_id": worker_id})
            job.status, job.message, job.error = "failed", "訓練失敗", str(exc)
            job.completed_at = datetime.now(timezone.utc)
            self._write_job(job, request)
            training_finished(job.status, started_at)
            self._logger.info(
                "Training job finished",
                extra={"event": "training.job.finished", "job_id": job_id, "model_id": job.result_model_id, "worker_id": worker_id},
            )
            raise
        try:
            job = self._complete_job(job, request, result, worker_id)
        except Exception:
            training_finished('confirmation_pending', started_at)
            raise
        training_finished(job.status, started_at)
        self._logger.info(
            "Training job finished",
            extra={"event": "training.job.finished", "job_id": job_id, "model_id": job.result_model_id, "worker_id": worker_id},
        )
        return job

    @job_state_transaction
    def schedule_retry(self, job_id: str, max_attempts: int, *, committed_output: bool = False) -> TrainingJob:
        """Move a failed job back to queued state when attempts remain."""

        job, request = self._read_job(job_id)
        if job.status != "failed" or (job.attempt >= max_attempts and not committed_output):
            return job
        job.status = "queued"
        job.progress = 0
        job.message = f"Retry scheduled ({job.attempt}/{max_attempts})"
        job.error = None
        job.started_at = None
        job.completed_at = None
        self._write_job(job, request)
        return job

    @job_state_transaction
    def cancel_job(self, job_id: str) -> TrainingJob:
        """Cancel a job that has not been claimed by a worker yet."""

        job, request = self._read_job(job_id)
        if job.status != "queued":
            raise PredictionValidationError("Only queued training jobs can be cancelled.")
        job.status = "cancelled"
        job.progress = 0
        job.message = "Training job cancelled"
        job.error = "Cancelled by operator"
        job.completed_at = datetime.now(timezone.utc)
        self._write_job(job, request)
        return job

    @job_state_transaction
    def requeue_failed_job(self, job_id: str) -> TrainingJob:
        """Called under queue locks; a durable preparation can safely be resumed."""

        job, request = self._read_job(job_id)
        if job.status == 'queued' and job.replay_pending:
            return job
        if job.status != "failed":
            raise PredictionValidationError("Only failed training jobs can be requeued.")
        job.status = "queued"
        job.progress = 0
        job.message = "Manual replay prepared; waiting for queue dispatch and worker claim"
        job.error = None
        job.started_at = None
        job.completed_at = None
        job.replay_pending = True
        self._write_job(job, request)
        return job

    def get_job(self, job_id: str) -> TrainingJob:
        return self._read_job(job_id)[0]

    def evaluate(self, model_id: str, dataset_id: str) -> ExternalEvaluationResult:
        with self._model_lock(model_id):
            return self._evaluate(model_id, dataset_id)

    def _evaluate(self, model_id: str, dataset_id: str) -> ExternalEvaluationResult:
        record = self.get(model_id)
        frame = self._datasets.frame(dataset_id)
        source = self._datasets.get(dataset_id)
        return self._evaluate_frame(record, frame, source.name, dataset_id)

    def evaluate_csv(self, model_id: str, content: bytes, filename: str) -> ExternalEvaluationResult:
        with self._model_lock(model_id):
            record = self.get(model_id)
            integer_columns = {feature['name']: object for feature in record.manifest.get('features', [])
                               if feature.get('dtype', '').lower().startswith(('int', 'uint'))}
            frame = read_prediction_csv(content, integer_columns)
            source_name = filename.replace('\\', '/').rsplit('/', 1)[-1]
            return self._evaluate_frame(record, frame, source_name)

    def _evaluate_frame(self, record: TrainedModelDetail, frame: pd.DataFrame,
                        source_name: str, dataset_id: str | None = None) -> ExternalEvaluationResult:
        required = record.feature_columns + [record.target_column]
        missing = [column for column in required if column not in frame]
        if missing: raise PredictionValidationError(f"外部測試集缺少欄位：{', '.join(missing)}")
        input_rows = len(frame)
        frame = clean_supervised_frame(frame, record.feature_columns, record.target_column, record.settings.get('numeric_imputer', 'median'))
        source = child_path(self._trained_root, record.id)
        pipeline = joblib.load(source / "model.pkl")
        try:
            actual = frame[record.target_column]
            if record.problem_type == 'regression': actual = pd.to_numeric(actual, errors='raise')
            predicted = pipeline.predict(frame[record.feature_columns])
            metrics = self._classification_metrics_from_predictions(actual, predicted) if record.problem_type == "classification" else self._metrics(actual, predicted)
        except ValueError as exc:
            raise PredictionValidationError('外部測試資料型態不正確：' + str(exc)) from exc
        context = TestEvaluationContext(source='dataset' if dataset_id else 'csv', source_name=source_name,
            dataset_id=dataset_id, input_rows=input_rows, evaluated_rows=len(frame),
            dropped_rows=input_rows - len(frame), evaluated_at=datetime.now(timezone.utc))
        payload = self._read_record(source)
        payload["test_metrics"] = metrics; payload["test_rmse"] = metrics.get("rmse")
        payload["test_r2"] = metrics.get("r2")
        payload['test_evaluation'] = context.model_dump(mode='json')
        write_json_atomic(source / "record.json", payload)
        return ExternalEvaluationResult(metrics=metrics, context=context)

    def _model_lock(self, model_id: str) -> FileLock:
        if model_id.startswith('.'):
            raise ModelNotFoundError('Internal staging models are not available.')
        child_path(self._trained_root, model_id)
        # Outside the model folder so deletion cannot unlink a held lock.
        with self._state_locks_guard:
            lock = self._model_locks.get(model_id)
            if lock is None:
                lock = FileLock(child_path(self._trained_root / '.locks', f'{model_id}.lock'))
                self._model_locks[model_id] = lock
            return lock

    def _write_job(self, job: TrainingJob, request: TrainingRequest) -> None:
        with self._job_state_lock(job.id):
            payload = {"job": job.model_dump(mode="json"), "request": request.model_dump(mode="json")}
            write_json_atomic(child_path(self._jobs_root, f'{job.id}.json'), payload)

    @job_state_transaction
    def _read_job(self, job_id: str) -> tuple[TrainingJob, TrainingRequest]:
        path = child_path(self._jobs_root, f'{job_id}.json')
        if not path.exists(): raise ModelNotFoundError(f"Training job '{job_id}' was not found.")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return TrainingJob.model_validate(payload["job"]), TrainingRequest.model_validate(payload["request"])

    def _update_job(self, job: TrainingJob, request: TrainingRequest, progress: int, message: str) -> None:
        with self._job_state_lock(job.id):
            current, saved_request = self._read_job(job.id)
            if current.status != 'running' or current.attempt != job.attempt:
                return
            current.progress, current.message = progress, message
            self._write_job(current, saved_request)
            job.progress, job.message = progress, message

    def _job_state_lock(self, job_id: str) -> FileLock:
        path = child_path(self._jobs_root / '.state-locks', f'{job_id}.lock')
        with self._state_locks_guard:
            lock = self._state_locks.get(job_id)
            if lock is None:
                lock = FileLock(path)
                self._state_locks[job_id] = lock
            return lock

    def list(self) -> list[TrainedModelSummary]:
        records = [TrainedModelSummary.model_validate(self._read_record(path.parent)) for path in self._trained_root.glob("*/record.json") if not path.parent.name.startswith('.')]
        return sorted(records, key=lambda item: item.completed_at, reverse=True)

    def get(self, model_id: str) -> TrainedModelDetail:
        if model_id.startswith('.'): raise ModelNotFoundError('Internal staging models are not available.')
        return TrainedModelDetail.model_validate(self._read_record(child_path(self._trained_root, model_id)))

    def publish(self, model_id: str) -> TrainedModelDetail:
        # Display names never participate in filesystem paths. Serialize publication
        # with rename/delete; publish an immutable artifact before changing the index.
        with FileLock(self._publish_root / '.publication.lock'), self._model_lock(model_id):
            record = self.get(model_id)
            source = child_path(self._trained_root, model_id)
            destination = child_path(self._publish_root, model_id)
            importance = None
            if (source / 'feature_importance.json').exists():
                try:
                    importance = read_importance(source, record.id, record.name)
                except ImportanceUnavailable as exc:
                    raise PredictionValidationError(str(exc)) from exc
            if destination.exists():
                metadata = json.loads((destination / 'metadata.json').read_text(encoding='utf-8'))
                if metadata.get('id') != model_id:
                    raise PredictionValidationError('Published package ID conflicts with the requested model.')
                if not (destination / record.manifest.get('artifact', 'model.pkl')).is_file():
                    raise PredictionValidationError('Existing published artifact is missing; restore the package before republishing.')
                # Explicit republishing refreshes the report snapshot, never the artifact.
                # GET remains read-only and does not fall back to mutable training data.
                if importance is not None:
                    save_importance(destination, importance)
            else:
                temporary = Path(tempfile.mkdtemp(prefix='.publish-', dir=self._publish_root))
                try:
                    shutil.copytree(source, temporary, dirs_exist_ok=True, ignore=shutil.ignore_patterns('record.json'))
                    temporary.rename(destination)
                finally:
                    if temporary.exists():
                        shutil.rmtree(temporary)
            published_manifest = ModelManifest.model_validate({**record.manifest, 'model_path': destination})
            if self._model_registry:
                self._model_registry.register(published_manifest, destination.name)
            payload = self._read_record(source)
            payload['status'] = 'published'
            write_json_atomic(source / 'record.json', payload)
            return TrainedModelDetail.model_validate(payload)

    def rename(self, model_id: str, name: str) -> TrainedModelDetail:
        with FileLock(self._publish_root / '.publication.lock'), self._model_lock(model_id):
            return self._rename(model_id, name)

    def _rename(self, model_id: str, name: str) -> TrainedModelDetail:
        source = child_path(self._trained_root, model_id)
        payload = self._read_record(source)
        payload["name"] = name.strip()
        payload["manifest"]["name"] = name.strip()
        write_json_atomic(source / "metadata.json", payload["manifest"])
        for metadata_path in self._publish_root.glob("*/metadata.json"):
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("id") == model_id:
                metadata["name"] = name.strip()
                write_json_atomic(metadata_path, metadata)
                if self._model_registry:
                    published_manifest = ModelManifest.model_validate({**metadata, "model_path": metadata_path.parent})
                    self._model_registry.update_manifest(published_manifest)
        write_json_atomic(source / "record.json", payload)
        return TrainedModelDetail.model_validate(payload)

    def delete_many(self, model_ids: list[str]) -> None:
        with FileLock(self._publish_root / '.publication.lock'):
            return self._delete_many(model_ids)

    def _delete_many(self, model_ids: list[str]) -> None:
        for model_id in model_ids:
            with self._model_lock(model_id):
                self._delete_one(model_id)

    def _delete_one(self, model_id: str) -> None:
        source = child_path(self._trained_root, model_id)
        self.get(model_id)
        for metadata_path in self._publish_root.glob("*/metadata.json"):
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("id") == model_id:
                shutil.rmtree(metadata_path.parent)
                if self._model_registry:
                    try:
                        self._model_registry.unregister(model_id)
                    except ModelNotFoundError:
                        pass
        shutil.rmtree(source)

    @staticmethod
    def _regression_metrics(target, predictions, scores) -> dict[str, float | None]:
        metrics = regression_metrics(target, predictions)
        metrics.update({
            "rmse_std": round(float(scores["test_rmse"].std()), 6),
            "cv_rmse_mean": round(float(-scores["test_rmse"].mean()), 6),
            "cv_mae_mean": round(float(-scores["test_mae"].mean()), 6),
            "cv_r2_mean": round(float(scores["test_r2"].mean()), 6),
        })
        return {key: value if value is None or np.isfinite(value) else None for key, value in metrics.items()}

    @staticmethod
    def _classification_metrics(target, predictions, scores, probabilities=None) -> dict[str, float]:
        metrics = {
            "accuracy": round(float(scores["test_accuracy"].mean()), 6),
            "f1": round(float(scores["test_f1"].mean()), 6),
            "precision": round(float(scores["test_precision"].mean()), 6),
            "recall": round(float(scores["test_recall"].mean()), 6),
        }
        if probabilities is not None:
            metrics["roc_auc"] = round(float(roc_auc_score(target, probabilities)), 6)
        return metrics

    @staticmethod
    def _classification_metrics_from_predictions(target, predictions) -> dict[str, float]:
        return {
            "accuracy": round(float(accuracy_score(target, predictions)), 6),
            "f1": round(float(f1_score(target, predictions, average="weighted")), 6),
            "precision": round(float(precision_score(target, predictions, average="weighted", zero_division=0)), 6),
            "recall": round(float(recall_score(target, predictions, average="weighted", zero_division=0)), 6),
        }

    def _external_test(self, pipeline: BaseEstimator, request: TrainingRequest) -> dict[str, float | None]:
        frame = self._datasets.frame(request.test_dataset_id)
        required = request.feature_columns + [request.target_column]
        missing = [name for name in required if name not in frame]
        if missing:
            raise PredictionValidationError(f"測試資料集缺少欄位：{', '.join(missing)}")
        frame = clean_supervised_frame(frame, request.feature_columns, request.target_column, request.numeric_imputer)
        actual = frame[request.target_column] if request.problem_type == "classification" else pd.to_numeric(frame[request.target_column], errors="raise")
        predicted = pipeline.predict(frame[request.feature_columns])
        return self._classification_metrics_from_predictions(actual, predicted) if request.problem_type == "classification" else self._metrics(actual, predicted)

    @staticmethod
    def _metrics(actual, predicted) -> dict[str, float | None]:
        return regression_metrics(actual, predicted)

    @staticmethod
    def _validate_request(frame: pd.DataFrame, request: TrainingRequest) -> None:
        classifier_algorithm = request.algorithm.endswith("_classifier") or request.algorithm == "logistic_regression"
        if request.problem_type == "classification" and not classifier_algorithm:
            raise PredictionValidationError("Classification 必須使用分類演算法。")
        if request.problem_type == "regression" and classifier_algorithm:
            raise PredictionValidationError("Regression 不能使用分類演算法。")
        if request.target_column not in frame:
            raise PredictionValidationError("找不到 target 欄位。")
        if request.target_column in request.feature_columns:
            raise PredictionValidationError("Target 欄位不能同時作為訓練特徵。")
        missing = [name for name in request.feature_columns if name not in frame]
        if missing:
            raise PredictionValidationError(f"找不到訓練欄位：{', '.join(missing)}")
        usable_target = frame.dropna(subset=[request.target_column])[request.target_column]
        if len(usable_target) < request.cv_folds:
            raise PredictionValidationError("可用資料列數不足以進行指定的交叉驗證折數。")
        if request.problem_type == "classification" and usable_target.nunique() < 2:
            raise PredictionValidationError("Classification target 至少需要兩個類別。")
        if request.problem_type == "classification" and usable_target.value_counts().min() < request.cv_folds:
            raise PredictionValidationError("每個 classification 類別的資料列數必須至少等於交叉驗證折數。")
        if request.problem_type == "regression" and not pd.api.types.is_numeric_dtype(frame[request.target_column]):
            raise PredictionValidationError("第一階段僅支援數值型 Regression target。")

    @staticmethod
    def _pipeline(features: pd.DataFrame, request: TrainingRequest) -> Pipeline:
        numeric = features.select_dtypes(include="number").columns.tolist()
        categorical = [name for name in features.columns if name not in numeric]
        transformers = []
        if numeric and request.numeric_imputer != "drop":
            kwargs = {"strategy": request.numeric_imputer}
            if request.numeric_imputer == "constant":
                kwargs["fill_value"] = request.numeric_constant
            transformers.append(("numeric", Pipeline([("imputer", SimpleImputer(**kwargs))]), numeric))
        elif numeric:
            transformers.append(("numeric", "passthrough", numeric))
        if categorical:
            kwargs = {"strategy": request.categorical_imputer}
            if request.categorical_imputer == "constant":
                kwargs["fill_value"] = request.categorical_constant
            transformers.append(("categorical", Pipeline([
                ("imputer", SimpleImputer(**kwargs)),
                ("encoder", OneHotEncoder(handle_unknown="ignore")),
            ]), categorical))
        preprocessor = ColumnTransformer(transformers)
        defaults = {
            "random_forest": RandomForestRegressor(n_estimators=200, random_state=42),
            "gradient_boosting": GradientBoostingRegressor(random_state=42),
            "xgboost": XGBRegressor(random_state=42, n_jobs=1),
            "adaboost": AdaBoostRegressor(random_state=42),
            "random_forest_classifier": RandomForestClassifier(n_estimators=200, random_state=42),
            "gradient_boosting_classifier": GradientBoostingClassifier(random_state=42),
            "xgboost_classifier": XGBClassifier(random_state=42, n_jobs=1, eval_metric="logloss"),
            "adaboost_classifier": AdaBoostClassifier(random_state=42),
            "logistic_regression": LogisticRegression(max_iter=1000),
        }
        steps = [("preprocess", preprocessor)]
        if request.dimension_reduction == "truncated_svd":
            steps.append(("reduction", TruncatedSVD(n_components=request.svd_components, random_state=42)))
        model = defaults[request.algorithm]
        allowed = {
            "random_forest": {"n_estimators", "min_samples_leaf", "max_depth", "min_samples_split", "max_leaf_nodes"}, "gradient_boosting": {"n_estimators", "learning_rate", "max_depth", "subsample"}, "xgboost": {"n_estimators", "verbosity", "learning_rate", "max_depth", "gamma", "subsample"}, "adaboost": {"n_estimators", "learning_rate", "loss"},
            "random_forest_classifier": {"n_estimators", "min_samples_leaf", "max_depth", "min_samples_split", "max_leaf_nodes"}, "gradient_boosting_classifier": {"n_estimators", "learning_rate", "max_depth", "subsample"}, "xgboost_classifier": {"n_estimators", "verbosity", "learning_rate", "max_depth", "gamma", "subsample"}, "adaboost_classifier": {"n_estimators", "learning_rate"}, "logistic_regression": {"penalty", "solver", "C"},
        }
        invalid = set(request.hyperparameters) - allowed[request.algorithm]
        if invalid: raise PredictionValidationError(f"不支援的超參數：{', '.join(invalid)}")
        model_params = dict(request.hyperparameters)
        if request.algorithm == "logistic_regression":
            for name in ("penalty", "solver"):
                if isinstance(model_params.get(name), str):
                    model_params[name] = model_params[name].lower()
            if model_params.get("penalty") == "l1" and "solver" not in model_params:
                model_params["solver"] = "liblinear"
            if model_params.get("penalty") == "l1" and model_params.get("solver") == "lbfgs":
                raise PredictionValidationError("Logistic Regression 使用 L1 penalty 時，solver 請改用 liblinear 或 saga。")
        if model_params: model.set_params(**model_params)
        steps.append(("model", model))
        pipeline = Pipeline(steps)
        return EncodedTargetClassifier(pipeline) if request.algorithm == "xgboost_classifier" else pipeline

    @staticmethod
    def _manifest(model_id, request, completed_at, validation, test_metrics, features: pd.DataFrame) -> dict:
        algorithm_names = {
            "random_forest": "Random Forest Regressor", "gradient_boosting": "Gradient Boosting Regressor", "xgboost": "XGBoost Regressor", "adaboost": "AdaBoost Regressor",
            "random_forest_classifier": "Random Forest Classifier", "gradient_boosting_classifier": "Gradient Boosting Classifier", "xgboost_classifier": "XGBoost Classifier", "adaboost_classifier": "AdaBoost Classifier", "logistic_regression": "Logistic Regression Classifier",
        }
        return {
            "id": model_id, "name": request.model_name, "version": "1.0.0", "framework": "sklearn",
            "problem_type": request.problem_type, "target": request.target_column,
            "features": [
                {"name": name, "dtype": str(features[name].dtype), "required": True}
                for name in request.feature_columns
            ],
            "prediction_column": "prediction", "author": "EdgeML Training", "created_at": completed_at.date().isoformat(),
            "description": f"{algorithm_names[request.algorithm]}; CV {('accuracy' if request.problem_type == 'classification' else 'RMSE')}: {validation.get('accuracy', validation.get('rmse'))}", "artifact": "model.pkl",
            "training_metrics": validation, "test_metrics": test_metrics,
        }

    @staticmethod
    def _read_record(path: Path) -> dict:
        record = path / "record.json"
        if not record.exists():
            raise ModelNotFoundError(f"Trained model '{path.name}' was not found.")
        return json.loads(record.read_text(encoding="utf-8"))
