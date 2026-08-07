from fastapi import APIRouter

from app.api.routes.models import router as models_router
from app.api.routes.predictions import router as predictions_router
from app.api.routes.datasets import router as datasets_router
from app.api.routes.training import router as training_router

api_router = APIRouter()
api_router.include_router(models_router, tags=["models"])
api_router.include_router(predictions_router, tags=["predictions"])
api_router.include_router(datasets_router, tags=["datasets"])
api_router.include_router(training_router, tags=["training"])
