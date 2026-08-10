from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

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
from sklearn.linear_model import Ridge
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_absolute_percentage_error,
    max_error,
    precision_score,
    r2_score,
    recall_score,
    root_mean_squared_error,
    roc_auc_score,
)
from sklearn.model_selection import KFold, StratifiedKFold, cross_val_predict, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, OneHotEncoder
from sklearn.decomposition import TruncatedSVD
from sklearn.base import BaseEstimator, ClassifierMixin, clone
from xgboost import XGBClassifier, XGBRegressor

from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.domain.model_catalog import ModelRegistry
from app.domain.schemas import ModelManifest
from app.domain.training_schemas import TrainedModelDetail, TrainedModelSummary, TrainingRequest
from app.domain.training_schemas import ExternalEvaluationResult, TrainingJob
from app.core.observability import training_finished, training_started
from app.services.dataset_service import DatasetService


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

    def train(self, request: TrainingRequest, progress=None) -> TrainedModelDetail:
        if progress: progress(10, "驗證資料與訓練設定")
        frame = self._datasets.frame(request.dataset_id)
        self._validate_request(frame, request)
        frame = frame.dropna(subset=[request.target_column]).copy()
        if request.numeric_imputer == "drop":
            frame = frame.dropna(subset=request.feature_columns)
        features = frame[request.feature_columns]
        target = frame[request.target_column] if request.problem_type == "classification" else pd.to_numeric(frame[request.target_column], errors="raise")
        pipeline = self._pipeline(features, request)
        if progress: progress(25, "進行交叉驗證")
        cv = self._cv(target, request)
        if request.problem_type == "classification":
            scores = cross_validate(
                pipeline, features, target, cv=cv,
                scoring={"accuracy": "accuracy", "f1": "f1_weighted", "precision": "precision_weighted", "recall": "recall_weighted"},
            )
        else:
            scores = cross_validate(
                pipeline, features, target, cv=cv,
                scoring={"rmse": "neg_root_mean_squared_error", "mae": "neg_mean_absolute_error", "r2": "r2"},
            )
        oof_predictions = cross_val_predict(pipeline, features, target, cv=cv)
        oof_probabilities = None
        if request.problem_type == "classification" and target.nunique() == 2:
            oof_probabilities = cross_val_predict(pipeline, features, target, cv=cv, method="predict_proba")[:, 1]
        validation = self._classification_metrics(target, oof_predictions, scores, oof_probabilities) if request.problem_type == "classification" else self._regression_metrics(target, oof_predictions, scores)
        if progress: progress(70, "以完整資料集訓練模型")
        pipeline.fit(features, target)
        if progress: progress(85, "儲存模型 artifact")
        validation_rmse = validation.get("rmse")
        validation_r2 = validation.get("r2")
        test_metrics = self._external_test(pipeline, request) if request.test_dataset_id else None
        model_id = str(uuid4())
        completed_at = datetime.now(timezone.utc)
        output_dir = self._trained_root / model_id
        output_dir.mkdir()
        joblib.dump(pipeline, output_dir / "model.pkl")
        manifest = self._manifest(model_id, request, completed_at, validation, test_metrics, features)
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
            "manifest": manifest,
        }
        (output_dir / "record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        (output_dir / "metadata.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (output_dir / "README.md").write_text(f"# {request.model_name}\n\nTrained by EdgeML.\n", encoding="utf-8")
        result = TrainedModelDetail.model_validate(record)
        if progress: progress(100, "訓練完成")
        return result

    def create_job(self, request: TrainingRequest) -> TrainingJob:
        job = TrainingJob(id=str(uuid4()), status="queued", progress=0, message="等待訓練開始")
        self._write_job(job, request)
        return job

    def run_job(self, job_id: str) -> None:
        job, request = self._read_job(job_id)
        started_at = training_started()
        self._logger.info("Training job started", extra={"event": "training.job.started", "job_id": job_id})
        job.status, job.progress, job.message = "running", 2, "準備訓練環境"
        self._write_job(job, request)
        try:
            result = self.train(request, lambda progress, message: self._update_job(job, request, progress, message))
            job.status, job.progress, job.message, job.result_model_id = "completed", 100, "訓練完成", result.id
        except Exception as exc:
            self._logger.exception("Training job failed", extra={"event": "training.job.failed", "job_id": job_id})
            job.status, job.message, job.error = "failed", "訓練失敗", str(exc)
        self._write_job(job, request)
        training_finished(job.status, started_at)
        self._logger.info(
            "Training job finished",
            extra={"event": "training.job.finished", "job_id": job_id, "model_id": job.result_model_id},
        )

    def get_job(self, job_id: str) -> TrainingJob:
        return self._read_job(job_id)[0]

    def evaluate(self, model_id: str, dataset_id: str) -> ExternalEvaluationResult:
        record = self.get(model_id)
        frame = self._datasets.frame(dataset_id)
        required = record.feature_columns + [record.target_column]
        missing = [column for column in required if column not in frame]
        if missing: raise PredictionValidationError(f"外部測試集缺少欄位：{', '.join(missing)}")
        frame = frame.dropna(subset=[record.target_column])
        pipeline = joblib.load(self._trained_root / model_id / "model.pkl")
        actual = frame[record.target_column]
        predicted = pipeline.predict(frame[record.feature_columns])
        metrics = self._classification_metrics_from_predictions(actual, predicted) if record.problem_type == "classification" else self._metrics(pd.to_numeric(actual, errors="raise"), predicted)
        payload = self._read_record(self._trained_root / model_id)
        payload["test_metrics"] = metrics; payload["test_rmse"] = metrics.get("rmse")
        payload["test_r2"] = metrics.get("r2")
        (self._trained_root / model_id / "record.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return ExternalEvaluationResult(metrics=metrics)

    def _write_job(self, job: TrainingJob, request: TrainingRequest) -> None:
        (self._jobs_root / f"{job.id}.json").write_text(json.dumps({"job": job.model_dump(), "request": request.model_dump()}, ensure_ascii=False), encoding="utf-8")

    def _read_job(self, job_id: str) -> tuple[TrainingJob, TrainingRequest]:
        path = self._jobs_root / f"{job_id}.json"
        if not path.exists(): raise ModelNotFoundError(f"Training job '{job_id}' was not found.")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return TrainingJob.model_validate(payload["job"]), TrainingRequest.model_validate(payload["request"])

    def _update_job(self, job: TrainingJob, request: TrainingRequest, progress: int, message: str) -> None:
        job.progress, job.message = progress, message; self._write_job(job, request)

    def list(self) -> list[TrainedModelSummary]:
        records = [TrainedModelSummary.model_validate(self._read_record(path.parent)) for path in self._trained_root.glob("*/record.json")]
        return sorted(records, key=lambda item: item.completed_at, reverse=True)

    def get(self, model_id: str) -> TrainedModelDetail:
        return TrainedModelDetail.model_validate(self._read_record(self._trained_root / model_id))

    def publish(self, model_id: str) -> TrainedModelDetail:
        record = self.get(model_id)
        source = self._trained_root / model_id
        destination = self._publish_root / f"{record.name}-{model_id[:8]}"
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination, ignore=shutil.ignore_patterns("record.json"))
        published_manifest = ModelManifest.model_validate({**record.manifest, "model_path": destination})
        if self._model_registry:
            self._model_registry.register(published_manifest, destination.name)
        payload = self._read_record(source)
        payload["status"] = "published"
        (source / "record.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return TrainedModelDetail.model_validate(payload)

    def rename(self, model_id: str, name: str) -> TrainedModelDetail:
        source = self._trained_root / model_id
        payload = self._read_record(source)
        payload["name"] = name.strip()
        payload["manifest"]["name"] = name.strip()
        (source / "record.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (source / "metadata.json").write_text(json.dumps(payload["manifest"], ensure_ascii=False, indent=2), encoding="utf-8")
        for metadata_path in self._publish_root.glob("*/metadata.json"):
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("id") == model_id:
                metadata["name"] = name.strip()
                metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
                if self._model_registry:
                    published_manifest = ModelManifest.model_validate({**metadata, "model_path": metadata_path.parent})
                    self._model_registry.update_manifest(published_manifest)
        return TrainedModelDetail.model_validate(payload)

    def delete_many(self, model_ids: list[str]) -> None:
        for model_id in model_ids:
            source = self._trained_root / model_id
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
    def _cv(target: pd.Series, request: TrainingRequest):
        if request.problem_type == "classification":
            return StratifiedKFold(n_splits=request.cv_folds, shuffle=True, random_state=42)
        return KFold(n_splits=request.cv_folds, shuffle=True, random_state=42)

    @staticmethod
    def _regression_metrics(target, predictions, scores) -> dict[str, float]:
        correlation = pd.Series(target).corr(pd.Series(predictions), method="pearson")
        return {
            "rmse": round(float(-scores["test_rmse"].mean()), 6),
            "mae": round(float(-scores["test_mae"].mean()), 6),
            "rmse_std": round(float(scores["test_rmse"].std()), 6),
            "r2": round(float(scores["test_r2"].mean()), 6),
            "pearson_r": 0.0 if pd.isna(correlation) else round(float(correlation), 6),
            "mape": round(float(mean_absolute_percentage_error(target, predictions) * 100), 6),
            "max_error": round(float(max_error(target, predictions)), 6),
            "target_mean": round(float(target.mean()), 6),
        }

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

    def _external_test(self, pipeline: BaseEstimator, request: TrainingRequest) -> dict[str, float]:
        frame = self._datasets.frame(request.test_dataset_id)
        required = request.feature_columns + [request.target_column]
        missing = [name for name in required if name not in frame]
        if missing:
            raise PredictionValidationError(f"測試資料集缺少欄位：{', '.join(missing)}")
        frame = frame.dropna(subset=[request.target_column])
        actual = frame[request.target_column] if request.problem_type == "classification" else pd.to_numeric(frame[request.target_column], errors="raise")
        predicted = pipeline.predict(frame[request.feature_columns])
        return self._classification_metrics_from_predictions(actual, predicted) if request.problem_type == "classification" else self._metrics(actual, predicted)

    @staticmethod
    def _metrics(actual, predicted) -> dict[str, float]:
        value_range = float(np.max(actual) - np.min(actual))
        rmse = float(root_mean_squared_error(actual, predicted))
        correlation = pd.Series(actual).corr(pd.Series(predicted), method="pearson")
        return {
            "mae": round(float(mean_absolute_error(actual, predicted)), 6),
            "mape": round(float(mean_absolute_percentage_error(actual, predicted) * 100), 6),
            "rmse": round(rmse, 6),
            "nrmse": round(rmse / value_range, 6) if value_range else 0.0,
            "max_error": round(float(max_error(actual, predicted)), 6),
            "target_mean": round(float(np.mean(actual)), 6),
            "pearson_r": 0.0 if pd.isna(correlation) else round(float(correlation), 6),
            "r2": round(float(r2_score(actual, predicted)), 6),
        }

    @staticmethod
    def _validate_request(frame: pd.DataFrame, request: TrainingRequest) -> None:
        classifier_algorithm = request.algorithm.endswith("_classifier")
        if request.problem_type == "classification" and not classifier_algorithm:
            raise PredictionValidationError("Classification 必須使用分類演算法。")
        if request.problem_type == "regression" and classifier_algorithm:
            raise PredictionValidationError("Regression 不能使用分類演算法。")
        if request.problem_type == "classification" and request.algorithm == "ridge":
            raise PredictionValidationError("Ridge 目前僅支援 Regression。")
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
            "ridge": Ridge(),
            "random_forest_classifier": RandomForestClassifier(n_estimators=200, random_state=42),
            "gradient_boosting_classifier": GradientBoostingClassifier(random_state=42),
            "xgboost_classifier": XGBClassifier(random_state=42, n_jobs=1, eval_metric="logloss"),
            "adaboost_classifier": AdaBoostClassifier(random_state=42),
        }
        steps = [("preprocess", preprocessor)]
        if request.dimension_reduction == "truncated_svd":
            steps.append(("reduction", TruncatedSVD(n_components=request.svd_components, random_state=42)))
        model = defaults[request.algorithm]
        allowed = {
            "random_forest": {"n_estimators", "max_depth", "min_samples_split"}, "gradient_boosting": {"n_estimators", "learning_rate", "max_depth", "subsample"}, "xgboost": {"n_estimators", "verbosity", "learning_rate", "max_depth", "gamma", "subsample"}, "adaboost": {"n_estimators", "learning_rate", "loss"}, "ridge": {"alpha"},
            "random_forest_classifier": {"n_estimators", "max_depth", "min_samples_split"}, "gradient_boosting_classifier": {"n_estimators", "learning_rate", "max_depth", "subsample"}, "xgboost_classifier": {"n_estimators", "verbosity", "learning_rate", "max_depth", "gamma", "subsample"}, "adaboost_classifier": {"n_estimators", "learning_rate"},
        }
        invalid = set(request.hyperparameters) - allowed[request.algorithm]
        if invalid: raise PredictionValidationError(f"不支援的超參數：{', '.join(invalid)}")
        if request.hyperparameters: model.set_params(**request.hyperparameters)
        steps.append(("model", model))
        pipeline = Pipeline(steps)
        return EncodedTargetClassifier(pipeline) if request.algorithm == "xgboost_classifier" else pipeline

    @staticmethod
    def _manifest(model_id, request, completed_at, validation, test_metrics, features: pd.DataFrame) -> dict:
        algorithm_names = {
            "random_forest": "Random Forest Regressor", "gradient_boosting": "Gradient Boosting Regressor", "xgboost": "XGBoost Regressor", "adaboost": "AdaBoost Regressor", "ridge": "Ridge Regressor",
            "random_forest_classifier": "Random Forest Classifier", "gradient_boosting_classifier": "Gradient Boosting Classifier", "xgboost_classifier": "XGBoost Classifier", "adaboost_classifier": "AdaBoost Classifier",
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
