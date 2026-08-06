from fastapi import APIRouter, Depends

from app.api.dependencies import get_prediction_service
from app.domain.schemas import ModelSummary
from app.services.prediction_service import PredictionService

router = APIRouter()


@router.get("/models", response_model=list[ModelSummary])
def list_models(service: PredictionService = Depends(get_prediction_service)) -> list[ModelSummary]:
    return service.list_models()

