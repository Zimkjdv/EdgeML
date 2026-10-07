from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from typing import Literal

from app.api.dependencies import get_prediction_service, get_published_feature_importance_service
from app.domain.errors import ModelNotFoundError
from app.domain.feature_importance import FeatureImportanceReport
from app.domain.schemas import ModelIdLookup, ModelSummary
from app.services.feature_importance_service import ImportanceUnavailable, PublishedFeatureImportanceService
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


@router.get('/models/{model_id}/feature-importance', response_model=FeatureImportanceReport,
            responses={200: {'content': {'text/csv': {}}}})
def get_published_feature_importance(
    model_id: str,
    format: Literal['json', 'csv'] = 'json',
    service: PublishedFeatureImportanceService = Depends(get_published_feature_importance_service),
):
    """Read the active prediction model's published importance snapshot."""
    try:
        report = service.get(model_id)
    except ModelNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ImportanceUnavailable as exc:
        raise HTTPException(409, str(exc)) from exc
    if format == 'csv':
        return Response(service.csv(report), media_type='text/csv',
                        headers={'Content-Disposition': 'attachment; filename="feature_importance.csv"'})
    return report
