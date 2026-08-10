from functools import lru_cache

from app.core.config import get_settings
from app.infrastructure.file_model_registry import FileModelRegistry
from app.infrastructure.file_prediction_history_repository import FilePredictionHistoryRepository
from app.infrastructure.predictor_factory import PredictorFactory
from app.infrastructure.redis_training_job_queue import RedisTrainingJobQueue
from app.domain.training_queue import TrainingJobQueue
from app.services.prediction_service import PredictionService
from app.services.dataset_service import DatasetService
from app.services.training_service import TrainingService
from app.services.model_registry_service import ModelRegistryService


def get_model_registry() -> FileModelRegistry:
    settings = get_settings()
    return FileModelRegistry(settings.model_registry_file, settings.models_root)


@lru_cache
def get_prediction_service() -> PredictionService:
    settings = get_settings()
    catalog = get_model_registry()
    history_repository = FilePredictionHistoryRepository(settings.prediction_history_file)
    return PredictionService(
        catalog=catalog,
        predictor_factory=PredictorFactory(),
        history_repository=history_repository,
    )


@lru_cache
def get_dataset_service() -> DatasetService:
    return DatasetService(get_settings().datasets_root)


@lru_cache
def get_training_service() -> TrainingService:
    settings = get_settings()
    return TrainingService(
        get_dataset_service(),
        settings.trained_models_root,
        settings.models_root,
        jobs_root=settings.training_jobs_root,
        model_registry=get_model_registry(),
    )


@lru_cache
def get_training_job_queue() -> TrainingJobQueue:
    settings = get_settings()
    if settings.queue_backend != "redis":
        raise RuntimeError(f"Unsupported training queue backend: {settings.queue_backend}")
    return RedisTrainingJobQueue(settings.redis_url, settings.training_queue_name)


@lru_cache
def get_model_registry_service() -> ModelRegistryService:
    return ModelRegistryService(get_model_registry())
