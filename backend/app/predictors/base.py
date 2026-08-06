from abc import ABC, abstractmethod

import pandas as pd

from app.domain.schemas import ModelManifest


class BasePredictor(ABC):
    """Framework adapter contract. API and services only depend on this abstraction."""

    @abstractmethod
    def load(self) -> None: ...

    @abstractmethod
    def predict(self, df: pd.DataFrame): ...

    def predict_proba(self, df: pd.DataFrame):
        return None

    def explain(self, df: pd.DataFrame):
        raise NotImplementedError("This predictor does not support explainability.")

    @abstractmethod
    def metadata(self) -> ModelManifest: ...

