from functools import lru_cache

from app.core.config import get_settings
from app.infrastructure.model_catalog import FileModelCatalog
from app.infrastructure.predictor_factory import PredictorFactory
from app.services.prediction_service import PredictionService


@lru_cache
def get_prediction_service() -> PredictionService:
    settings = get_settings()
    catalog = FileModelCatalog(settings.models_root)
    return PredictionService(catalog=catalog, predictor_factory=PredictorFactory())

