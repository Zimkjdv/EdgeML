from fastapi import APIRouter

from app.api.routes.models import router as models_router
from app.api.routes.predictions import router as predictions_router

api_router = APIRouter()
api_router.include_router(models_router, tags=["models"])
api_router.include_router(predictions_router, tags=["predictions"])

