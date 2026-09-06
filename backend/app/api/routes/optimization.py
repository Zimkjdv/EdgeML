from fastapi import APIRouter, Depends, HTTPException
from app.api.dependencies import get_optimization_service
from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.domain.optimization import OptimizationRequest, OptimizationResult
from app.services.optimization_service import OptimizationService

router = APIRouter(prefix='/optimization')


@router.get('/models')
def models(service: OptimizationService = Depends(get_optimization_service)):
    return [m for m in service.catalog.list() if m.problem_type == 'regression']


@router.post('/simulate', response_model=OptimizationResult)
def simulate(request: OptimizationRequest, service: OptimizationService = Depends(get_optimization_service)):
    try:
        return service.run(request)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PredictionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get('/models/{model_id}/defaults')
def defaults(model_id: str, service: OptimizationService = Depends(get_optimization_service)):
    try:
        return service.feature_defaults(model_id)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
