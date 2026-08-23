from functools import lru_cache
import secrets

from fastapi import HTTPException, Request, status

from app.core.config import get_settings
from app.infrastructure.file_model_registry import FileModelRegistry
from app.infrastructure.file_prediction_history_repository import FilePredictionHistoryRepository
from app.infrastructure.predictor_factory import PredictorFactory
from app.infrastructure.redis_training_job_queue import RedisTrainingJobQueue
from app.domain.training_queue import TrainingJobQueue, TrainingQueueOperations
from app.services.prediction_service import PredictionService
from app.services.dataset_service import DatasetService
from app.services.training_service import TrainingService
from app.services.model_registry_service import ModelRegistryService
from app.services.queue_operations_service import QueueOperationsService


def require_api_token(request: Request) -> None:
    """Optionally protect API routes with a configured bearer/API token.

    Authentication is disabled when ``EDGEML_API_TOKEN`` is unset, preserving
    the local development experience. Health endpoints are intentionally not
    included in the ``/api`` router dependency and remain probeable.
    """

    expected = get_settings().api_token
    if not expected:
        return

    authorization = request.headers.get("authorization", "")
    supplied = authorization[7:].strip() if authorization.lower().startswith("bearer ") else request.headers.get("x-api-key", "")
    if supplied and secrets.compare_digest(supplied, expected):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="A valid API token is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


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
def get_queue_operations_service() -> QueueOperationsService:
    settings = get_settings()
    queue = get_training_job_queue()
    # RedisTrainingJobQueue implements both the dispatch and operations boundaries.
    operations: TrainingQueueOperations = queue  # type: ignore[assignment]
    return QueueOperationsService(operations, get_training_service(), settings.training_queue_name)


@lru_cache
def get_model_registry_service() -> ModelRegistryService:
    return ModelRegistryService(get_model_registry())
