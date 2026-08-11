from fastapi import APIRouter

from app.api.routes.models import router as models_router
from app.api.routes.predictions import router as predictions_router
from app.api.routes.datasets import router as datasets_router
from app.api.routes.training import router as training_router
from app.api.routes.registry import router as registry_router
from app.api.routes.queue import router as queue_router

api_router = APIRouter()
api_router.include_router(models_router, tags=["models"])
api_router.include_router(predictions_router, tags=["predictions"])
api_router.include_router(datasets_router, tags=["datasets"])
api_router.include_router(training_router, tags=["training"])
api_router.include_router(registry_router, tags=["model-registry"])
api_router.include_router(queue_router, tags=["queue-operations"])
