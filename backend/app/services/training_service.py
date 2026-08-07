from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import AdaBoostRegressor, GradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, max_error, r2_score, root_mean_squared_error
from sklearn.model_selection import KFold, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.decomposition import TruncatedSVD
from xgboost import XGBRegressor

from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.domain.training_schemas import TrainedModelDetail, TrainedModelSummary, TrainingRequest
from app.domain.training_schemas import ExternalEvaluationResult, TrainingJob
from app.services.dataset_service import DatasetService


class TrainingService:
    def __init__(self, datasets: DatasetService, trained_models_root: Path, publish_root: Path, jobs_root: Path | None = None) -> None:
        self._datasets = datasets
        self._trained_root = trained_models_root
        self._publish_root = publish_root
        self._trained_root.mkdir(parents=True, exist_ok=True)
        self._publish_root.mkdir(parents=True, exist_ok=True)
        self._jobs_root = jobs_root or trained_models_root.parent / "training_jobs"
        self._jobs_root.mkdir(parents=True, exist_ok=True)

    def train(self, request: TrainingRequest, progress=None) -> TrainedModelDetail:
        if progress: progress(10, "驗證資料與訓練設定")
        frame = self._datasets.frame(request.dataset_id)
        self._validate_request(frame, request)
        frame = frame.dropna(subset=[request.target_column]).copy()
        if request.numeric_imputer == "drop":
            frame = frame.dropna(subset=request.feature_columns)
        features = frame[request.feature_columns]
        target = pd.to_numeric(frame[request.target_column], errors="raise")
        pipeline = self._pipeline(features, request)
        if progress: progress(25, "進行交叉驗證")
        cv = KFold(n_splits=request.cv_folds, shuffle=True, random_state=42)
        scores = cross_validate(
            pipeline, features, target, cv=cv,
            scoring={"rmse": "neg_root_mean_squared_error", "mae": "neg_mean_absolute_error", "r2": "r2"},
        )
        if progress: progress(70, "以完整資料集訓練模型")
        pipeline.fit(features, target)
        if progress: progress(85, "儲存模型 artifact")
        validation = {
            "rmse": round(float(-scores["test_rmse"].mean()), 6),
            "mae": round(float(-scores["test_mae"].mean()), 6),
            "rmse_std": round(float(scores["test_rmse"].std()), 6),
            "r2": round(float(scores["test_r2"].mean()), 6),
        }
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
            "problem_type": "regression",
            "validation_rmse": validation["rmse"],
            "test_rmse": test_metrics["rmse"] if test_metrics else None,
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
        job.status, job.progress, job.message = "running", 2, "準備訓練環境"
        self._write_job(job, request)
        try:
            result = self.train(request, lambda progress, message: self._update_job(job, request, progress, message))
            job.status, job.progress, job.message, job.result_model_id = "completed", 100, "訓練完成", result.id
        except Exception as exc:
            job.status, job.message, job.error = "failed", "訓練失敗", str(exc)
        self._write_job(job, request)

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
        actual = pd.to_numeric(frame[record.target_column], errors="raise")
        metrics = self._metrics(actual, pipeline.predict(frame[record.feature_columns]))
        payload = self._read_record(self._trained_root / model_id)
        payload["test_metrics"] = metrics; payload["test_rmse"] = metrics["rmse"]
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
        return TrainedModelDetail.model_validate(payload)

    def delete_many(self, model_ids: list[str]) -> None:
        for model_id in model_ids:
            source = self._trained_root / model_id
            self.get(model_id)
            for metadata_path in self._publish_root.glob("*/metadata.json"):
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if metadata.get("id") == model_id:
                    shutil.rmtree(metadata_path.parent)
            shutil.rmtree(source)

    def _external_test(self, pipeline: Pipeline, request: TrainingRequest) -> dict[str, float]:
        frame = self._datasets.frame(request.test_dataset_id)
        required = request.feature_columns + [request.target_column]
        missing = [name for name in required if name not in frame]
        if missing:
            raise PredictionValidationError(f"測試資料集缺少欄位：{', '.join(missing)}")
        frame = frame.dropna(subset=[request.target_column])
        actual = pd.to_numeric(frame[request.target_column], errors="raise")
        predicted = pipeline.predict(frame[request.feature_columns])
        return self._metrics(actual, predicted)

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
        if request.target_column not in frame:
            raise PredictionValidationError("找不到 target 欄位。")
        if request.target_column in request.feature_columns:
            raise PredictionValidationError("Target 欄位不能同時作為訓練特徵。")
        missing = [name for name in request.feature_columns if name not in frame]
        if missing:
            raise PredictionValidationError(f"找不到訓練欄位：{', '.join(missing)}")
        if len(frame.dropna(subset=[request.target_column])) < request.cv_folds:
            raise PredictionValidationError("可用資料列數不足以進行指定的交叉驗證折數。")
        if not pd.api.types.is_numeric_dtype(frame[request.target_column]):
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
        }
        steps = [("preprocess", preprocessor)]
        if request.dimension_reduction == "truncated_svd":
            steps.append(("reduction", TruncatedSVD(n_components=request.svd_components, random_state=42)))
        model = defaults[request.algorithm]
        allowed = {"random_forest": {"n_estimators", "max_depth", "min_samples_split"}, "gradient_boosting": {"n_estimators", "learning_rate", "max_depth", "subsample"}, "xgboost": {"n_estimators", "verbosity", "learning_rate", "max_depth", "gamma", "subsample"}, "adaboost": {"n_estimators", "learning_rate", "loss"}}
        invalid = set(request.hyperparameters) - allowed[request.algorithm]
        if invalid: raise PredictionValidationError(f"不支援的超參數：{', '.join(invalid)}")
        if request.hyperparameters: model.set_params(**request.hyperparameters)
        steps.append(("model", model))
        return Pipeline(steps)

    @staticmethod
    def _manifest(model_id, request, completed_at, validation, test_metrics, features: pd.DataFrame) -> dict:
        algorithm_names = {
            "random_forest": "Random Forest Regressor", "gradient_boosting": "Gradient Boosting Regressor",
            "xgboost": "XGBoost Regressor", "adaboost": "AdaBoost Regressor",
        }
        return {
            "id": model_id, "name": request.model_name, "version": "1.0.0", "framework": "sklearn",
            "problem_type": "regression", "target": request.target_column,
            "features": [
                {"name": name, "dtype": str(features[name].dtype), "required": True}
                for name in request.feature_columns
            ],
            "prediction_column": "prediction", "author": "EdgeML Training", "created_at": completed_at.date().isoformat(),
            "description": f"{algorithm_names[request.algorithm]}; CV RMSE: {validation['rmse']}", "artifact": "model.pkl",
            "training_metrics": validation, "test_metrics": test_metrics,
        }

    @staticmethod
    def _read_record(path: Path) -> dict:
        record = path / "record.json"
        if not record.exists():
            raise ModelNotFoundError(f"Trained model '{path.name}' was not found.")
        return json.loads(record.read_text(encoding="utf-8"))
