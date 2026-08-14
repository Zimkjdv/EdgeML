from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_prediction_service
from app.domain.errors import ModelNotFoundError
from app.domain.schemas import ModelIdLookup, ModelSummary
from app.services.prediction_service import PredictionService

router = APIRouter()


@router.get("/models", response_model=list[ModelSummary])
def list_models(service: PredictionService = Depends(get_prediction_service)) -> list[ModelSummary]:
    return service.list_models()


@router.get("/models/ids", response_model=list[str])
def list_model_ids(service: PredictionService = Depends(get_prediction_service)) -> list[str]:
    """Return the identifiers of all active models available for prediction."""
    return service.list_model_ids()


@router.get("/models/by-name/{model_name}", response_model=ModelIdLookup)
def get_model_id_by_name(
    model_name: str,
    service: PredictionService = Depends(get_prediction_service),
) -> ModelIdLookup:
    """Resolve an active model's display name to its stable model id."""
    try:
        model_id = service.model_id_by_name(model_name)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ModelIdLookup(name=model_name, id=model_id)
