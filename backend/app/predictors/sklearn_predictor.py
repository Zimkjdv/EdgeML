from pathlib import Path

import joblib
import pandas as pd

from app.domain.schemas import ModelManifest
from app.predictors.base import BasePredictor


class SklearnPredictor(BasePredictor):
    def __init__(self, manifest: ModelManifest) -> None:
        self._manifest = manifest
        self._model = None
        self._preprocessor = None

    def load(self) -> None:
        self._model = joblib.load(Path(self._manifest.model_path) / self._manifest.artifact)
        if self._manifest.preprocess_artifact:
            self._preprocessor = joblib.load(
                Path(self._manifest.model_path) / self._manifest.preprocess_artifact
            )

    def predict(self, df: pd.DataFrame):
        if self._model is None:
            self.load()
        data = self._preprocessor.transform(df) if self._preprocessor else df
        return self._model.predict(data)

    def predict_proba(self, df: pd.DataFrame):
        if self._model is None:
            self.load()
        if not hasattr(self._model, "predict_proba"):
            return None
        data = self._preprocessor.transform(df) if self._preprocessor else df
        return self._model.predict_proba(data)

    def metadata(self) -> ModelManifest:
        return self._manifest

