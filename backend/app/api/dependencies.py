from functools import lru_cache

from app.core.config import get_settings
from app.infrastructure.model_catalog import FileModelCatalog
from app.infrastructure.predictor_factory import PredictorFactory
from app.services.prediction_service import PredictionService
from app.services.dataset_service import DatasetService
from app.services.training_service import TrainingService


@lru_cache
def get_prediction_service() -> PredictionService:
    settings = get_settings()
    catalog = FileModelCatalog(settings.models_root)
    return PredictionService(catalog=catalog, predictor_factory=PredictorFactory())


@lru_cache
def get_dataset_service() -> DatasetService:
    return DatasetService(get_settings().datasets_root)


@lru_cache
def get_training_service() -> TrainingService:
    settings = get_settings()
    return TrainingService(get_dataset_service(), settings.trained_models_root, settings.models_root)
