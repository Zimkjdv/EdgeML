from functools import lru_cache
from typing import Literal
import secrets

from fastapi import Depends, HTTPException, Request, status

from app.core.config import get_settings
from app.infrastructure.file_model_registry import FileModelRegistry
from app.infrastructure.file_prediction_history_repository import FilePredictionHistoryRepository
from app.infrastructure.predictor_factory import PredictorFactory
from app.infrastructure.redis_training_job_queue import RedisTrainingJobQueue
from app.repositories.api_token import SqliteApiTokenRepository
from app.services.api_token_service import ApiTokenService
from app.domain.training_queue import TrainingJobQueue, TrainingQueueOperations
from app.services.prediction_service import PredictionService
from app.services.dataset_service import DatasetService
from app.services.training_service import TrainingService
from app.services.model_registry_service import ModelRegistryService
from app.services.queue_operations_service import QueueOperationsService
from app.infrastructure.trained_model_catalog import TrainedModelCatalog
from app.services.optimization_service import OptimizationService
from app.services.optimization_defaults import OptimizationDefaults


def get_optimization_service(source: Literal['trained', 'registry'] = 'trained') -> OptimizationService:
    settings = get_settings()
    catalog = TrainedModelCatalog(settings.trained_models_root) if source == 'trained' else get_model_registry()
    return OptimizationService(catalog, PredictorFactory(), settings.optimization_population, settings.optimization_iterations,
        OptimizationDefaults(settings.trained_models_root, get_dataset_service()))


@lru_cache
def get_api_token_service() -> ApiTokenService:
    return ApiTokenService(SqliteApiTokenRepository(get_settings().api_tokens_database))


def require_api_token(
    request: Request,
    service: ApiTokenService = Depends(get_api_token_service),
) -> None:
    """Optionally protect API routes with a configured bearer/API token.

    Authentication is disabled when ``EDGEML_API_TOKEN`` is unset, preserving
    the local development experience. Health endpoints are intentionally not
    included in the ``/api`` router dependency and remain probeable.
    """

    supplied = _request_token(request)
    expected = get_settings().api_token
    if expected and supplied and secrets.compare_digest(supplied, expected):
        return
    if supplied:
        record = service.authenticate(supplied)
        if record and ("api" in record.scopes or request.url.path.startswith("/api/auth/tokens")):
            return
    # Keep a clean local install usable until its first token is created.
    if not expected and not service.has_active_tokens():
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="A valid API token is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_token_management(
    request: Request,
    service: ApiTokenService = Depends(get_api_token_service),
) -> None:
    """Require the bootstrap token or a token carrying ``tokens:manage``."""

    supplied = _request_token(request)
    expected = get_settings().api_token
    if expected and supplied and secrets.compare_digest(supplied, expected):
        return
    if supplied:
        record = service.authenticate(supplied)
        if record and "tokens:manage" in record.scopes:
            return
    if not expected and not service.has_active_tokens():
        raise HTTPException(status_code=503, detail="Set EDGEML_API_TOKEN before creating the first managed token.")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token management permission is required.")


def _request_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return request.headers.get("x-api-key", "").strip()


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
