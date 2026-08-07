from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.api.dependencies import get_training_service
from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.domain.training_schemas import DatasetRenameRequest, ExternalEvaluationRequest, ExternalEvaluationResult, TrainedModelDetail, TrainedModelSummary, TrainingJob, TrainingRequest
from app.services.training_service import TrainingService

router = APIRouter()


@router.post("/training", response_model=TrainedModelDetail, status_code=201)
def train(request: TrainingRequest, service: TrainingService = Depends(get_training_service)) -> TrainedModelDetail:
    try:
        return service.train(request)
    except (ModelNotFoundError, PredictionValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/training/jobs", response_model=TrainingJob, status_code=202)
def create_training_job(request: TrainingRequest, background_tasks: BackgroundTasks, service: TrainingService = Depends(get_training_service)) -> TrainingJob:
    job = service.create_job(request)
    background_tasks.add_task(service.run_job, job.id)
    return job


@router.get("/training/jobs/{job_id}", response_model=TrainingJob)
def get_training_job(job_id: str, service: TrainingService = Depends(get_training_service)) -> TrainingJob:
    try: return service.get_job(job_id)
    except ModelNotFoundError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/trained-models", response_model=list[TrainedModelSummary])
def list_trained_models(service: TrainingService = Depends(get_training_service)) -> list[TrainedModelSummary]:
    return service.list()


@router.get("/trained-models/{model_id}", response_model=TrainedModelDetail)
def get_trained_model(model_id: str, service: TrainingService = Depends(get_training_service)) -> TrainedModelDetail:
    try:
        return service.get(model_id)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/trained-models/{model_id}", response_model=TrainedModelDetail)
def rename_trained_model(model_id: str, request: DatasetRenameRequest, service: TrainingService = Depends(get_training_service)) -> TrainedModelDetail:
    try: return service.rename(model_id, request.name)
    except ModelNotFoundError as exc: raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/trained-models/{model_id}/publish", response_model=TrainedModelDetail)
def publish_trained_model(
    model_id: str, service: TrainingService = Depends(get_training_service)
) -> TrainedModelDetail:
    try:
        return service.publish(model_id)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/trained-models/{model_id}/evaluate", response_model=ExternalEvaluationResult)
def evaluate_trained_model(model_id: str, request: ExternalEvaluationRequest, service: TrainingService = Depends(get_training_service)) -> ExternalEvaluationResult:
    try: return service.evaluate(model_id, request.dataset_id)
    except (ModelNotFoundError, PredictionValidationError) as exc: raise HTTPException(status_code=422, detail=str(exc)) from exc
