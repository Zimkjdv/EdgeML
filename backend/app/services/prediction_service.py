from io import BytesIO
from datetime import datetime, timezone
from uuid import uuid4

import pandas as pd

from app.domain.errors import PredictionValidationError
from app.domain.schemas import ModelSummary, PredictionHistoryRecord, PredictionOutput
from app.infrastructure.model_catalog import FileModelCatalog
from app.infrastructure.predictor_factory import PredictorFactory
from app.repositories.prediction_history import PredictionHistoryRepository


class PredictionService:
    def __init__(
        self,
        catalog: FileModelCatalog,
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

    def predict_csv(self, model_id: str, content: bytes, source_filename: str = "input.csv") -> PredictionOutput:
        manifest = self._catalog.get(model_id)
        try:
            frame = pd.read_csv(BytesIO(content))
        except (UnicodeDecodeError, pd.errors.ParserError, ValueError) as exc:
            raise PredictionValidationError("The uploaded file is not a valid UTF-8 CSV.") from exc

        self._validate_frame(frame, manifest.features)
        feature_frame = frame[[feature.name for feature in manifest.features]]
        predictor = self._predictor_factory.create(manifest)
        frame[manifest.prediction_column] = predictor.predict(feature_frame)
        csv_content = frame.to_csv(index=False).encode("utf-8")
        self._history_repository.add(
            PredictionHistoryRecord(
                id=str(uuid4()),
                model_id=manifest.id,
                model_name=manifest.name,
                source_filename=source_filename.replace("\\", "/").rsplit("/", 1)[-1],
                row_count=len(frame),
                created_at=datetime.now(timezone.utc),
            )
        )
        return PredictionOutput(filename=f"{manifest.name}_predictions.csv", csv_content=csv_content)

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
                if converted.isna().any():
                    raise PredictionValidationError(
                        f"Column '{feature.name}' must contain {feature.dtype} values."
                    )
                frame[feature.name] = converted.astype(feature.dtype)

