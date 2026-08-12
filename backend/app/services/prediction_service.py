from io import BytesIO
from datetime import datetime, timezone
from uuid import uuid4

import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, mean_absolute_percentage_error, max_error, precision_score, r2_score, recall_score, root_mean_squared_error

from app.domain.errors import PredictionValidationError
from app.domain.model_catalog import ModelCatalog
from app.domain.schemas import JsonPredictionOutput, ModelSummary, PredictionHistoryRecord, PredictionOutput
from app.infrastructure.predictor_factory import PredictorFactory
from app.repositories.prediction_history import PredictionHistoryRepository


class PredictionService:
    def __init__(
        self,
        catalog: ModelCatalog,
        predictor_factory: PredictorFactory,
        history_repository: PredictionHistoryRepository,
    ) -> None:
        self._catalog = catalog
        self._predictor_factory = predictor_factory
        self._history_repository = history_repository

    def list_models(self) -> list[ModelSummary]:
        return self._catalog.list()

    def list_history(self) -> list[PredictionHistoryRecord]:
        return self._history_repository.list()

    def predict_csv(self, model_id: str, content: bytes, source_filename: str = "input.csv", ground_truth_column: str | None = None) -> PredictionOutput:
        manifest = self._catalog.get(model_id)
        try:
            frame = pd.read_csv(BytesIO(content))
        except (UnicodeDecodeError, pd.errors.ParserError, ValueError) as exc:
            raise PredictionValidationError("The uploaded file is not a valid UTF-8 CSV.") from exc

        frame, predictions, metrics, evaluation_column, dropped_rows = self._predict_frame(frame, manifest, ground_truth_column)
        frame[manifest.prediction_column] = predictions
        if manifest.problem_type == "regression":
            frame[manifest.prediction_column] = pd.Series(predictions, index=frame.index).round(4)
        if evaluation_column and manifest.problem_type == "regression":
            actual_numeric = pd.to_numeric(frame[evaluation_column], errors="raise")
            frame["prediction_error"] = (pd.Series(predictions, index=frame.index) - actual_numeric).round(4)
        elif evaluation_column:
            frame["prediction_correct"] = predictions == frame[evaluation_column]
        csv_content = frame.to_csv(index=False).encode("utf-8")
        self._record_history(manifest, source_filename, len(frame))
        return PredictionOutput(filename=f"{manifest.name}_predictions.csv", csv_content=csv_content, metrics=metrics, ground_truth_column=evaluation_column, dropped_rows=dropped_rows)

    def predict_json(self, model_id: str, records: list[dict], source_name: str | None = None, ground_truth_column: str | None = None) -> JsonPredictionOutput:
        manifest = self._catalog.get(model_id)
        frame = pd.DataFrame(records)
        frame, predictions, metrics, evaluation_column, dropped_rows = self._predict_frame(frame, manifest, ground_truth_column)
        frame[manifest.prediction_column] = predictions
        if manifest.problem_type == "regression":
            frame[manifest.prediction_column] = pd.Series(predictions, index=frame.index).round(4)
        if evaluation_column and manifest.problem_type == "regression":
            actual_numeric = pd.to_numeric(frame[evaluation_column], errors="raise")
            frame["prediction_error"] = (pd.Series(predictions, index=frame.index) - actual_numeric).round(4)
        elif evaluation_column:
            frame["prediction_correct"] = predictions == frame[evaluation_column]
        # Convert pandas/numpy values to JSON-safe Python values, including nulls.
        output_frame = frame.astype(object).where(pd.notna(frame), None)
        self._record_history(manifest, source_name or "json-api", len(frame))
        return JsonPredictionOutput(
            model_id=manifest.id,
            model_name=manifest.name,
            prediction_column=manifest.prediction_column,
            records=output_frame.to_dict(orient="records"),
            metrics=metrics,
            ground_truth_column=evaluation_column,
            dropped_rows=dropped_rows,
        )

    def _predict_frame(self, frame: pd.DataFrame, manifest, ground_truth_column: str | None):
        self._validate_frame(frame, manifest.features)
        # ``None`` means automatic detection (the manifest target is preferred).
        # An empty form value explicitly disables evaluation, which lets the UI
        # handle files that happen to contain a target column but should not be
        # scored.
        evaluation_column = (
            None
            if ground_truth_column == ""
            else ground_truth_column or (manifest.target if manifest.target in frame.columns else None)
        )
        if evaluation_column and evaluation_column in {feature.name for feature in manifest.features}:
            raise PredictionValidationError("Ground Truth 欄位不能同時作為模型輸入特徵。")
        if evaluation_column and evaluation_column not in frame.columns:
            raise PredictionValidationError(f"找不到 Ground Truth 欄位：{evaluation_column}。")
        required_columns = [feature.name for feature in manifest.features if feature.required]
        rows_before_cleaning = len(frame)
        drop_columns = required_columns + ([evaluation_column] if evaluation_column else [])
        frame = frame.loc[~frame[drop_columns].isna().any(axis=1)].copy()
        dropped_rows = rows_before_cleaning - len(frame)
        if frame.empty:
            raise PredictionValidationError("CSV 清理缺值資料列後，沒有可預測的資料。")
        feature_frame = frame[[feature.name for feature in manifest.features]]
        predictor = self._predictor_factory.create(manifest)
        predictions = predictor.predict(feature_frame)
        metrics: dict[str, float] = {}
        if evaluation_column:
            metrics = self._evaluate_predictions(manifest.problem_type, frame[evaluation_column], predictions)
        return frame, predictions, metrics, evaluation_column, dropped_rows

    def _record_history(self, manifest, source_filename: str, row_count: int) -> None:
        self._history_repository.add(
            PredictionHistoryRecord(
                id=str(uuid4()),
                model_id=manifest.id,
                model_name=manifest.name,
                source_filename=source_filename.replace("\\", "/").rsplit("/", 1)[-1],
                row_count=row_count,
                created_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    def _evaluate_predictions(problem_type: str, actual, predictions) -> dict[str, float]:
        if problem_type == "classification":
            return {
                "accuracy": round(float(accuracy_score(actual, predictions)), 6),
                "precision": round(float(precision_score(actual, predictions, average="weighted", zero_division=0)), 6),
                "recall": round(float(recall_score(actual, predictions, average="weighted", zero_division=0)), 6),
                "f1": round(float(f1_score(actual, predictions, average="weighted", zero_division=0)), 6),
            }
        actual_numeric = pd.to_numeric(actual, errors="raise")
        correlation = pd.Series(actual_numeric).corr(pd.Series(predictions), method="pearson")
        return {
            "mae": round(float(mean_absolute_error(actual_numeric, predictions)), 6),
            "mape": round(float(mean_absolute_percentage_error(actual_numeric, predictions) * 100), 6),
            "rmse": round(float(root_mean_squared_error(actual_numeric, predictions)), 6),
            "max_error": round(float(max_error(actual_numeric, predictions)), 6),
            "r2": round(float(r2_score(actual_numeric, predictions)), 6),
            "pearson_r": 0.0 if pd.isna(correlation) else round(float(correlation), 6),
        }

    @staticmethod
    def _validate_frame(frame: pd.DataFrame, features) -> None:
        missing = [feature.name for feature in features if feature.required and feature.name not in frame]
        if missing:
            raise PredictionValidationError(f"CSV is missing required columns: {', '.join(missing)}.")
        if frame.empty:
            raise PredictionValidationError("CSV must contain at least one data row.")
        for feature in features:
            if feature.name not in frame:
                continue
            if feature.dtype.startswith(("float", "int")):
                converted = pd.to_numeric(frame[feature.name], errors="coerce")
                invalid = converted.isna() & frame[feature.name].notna()
                if invalid.any():
                    raise PredictionValidationError(
                        f"Column '{feature.name}' must contain {feature.dtype} values."
                    )
                frame[feature.name] = converted if converted.isna().any() else converted.astype(feature.dtype)
