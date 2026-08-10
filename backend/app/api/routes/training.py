from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_training_job_queue, get_training_service
from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.domain.training_queue import TrainingJobQueue
from app.domain.training_schemas import DatasetRenameRequest, ExternalEvaluationRequest, ExternalEvaluationResult, TrainedModelDeleteRequest, TrainedModelDetail, TrainedModelSummary, TrainingJob, TrainingRequest
from app.services.training_service import TrainingService

router = APIRouter()


@router.post("/training", response_model=TrainedModelDetail, status_code=201)
def train(request: TrainingRequest, service: TrainingService = Depends(get_training_service)) -> TrainedModelDetail:
    try:
        return service.train(request)
    except (ModelNotFoundError, PredictionValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/training/jobs", response_model=TrainingJob, status_code=202)
def create_training_job(
    request: TrainingRequest,
    service: TrainingService = Depends(get_training_service),
    queue: TrainingJobQueue = Depends(get_training_job_queue),
) -> TrainingJob:
    job = service.create_job(request)
    try:
        queue.enqueue(job.id)
    except Exception as exc:
        service.mark_job_failed(job.id, str(exc))
        raise HTTPException(status_code=503, detail="Training queue is unavailable.") from exc
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


@router.delete("/trained-models", status_code=204)
def delete_trained_models(request: TrainedModelDeleteRequest, service: TrainingService = Depends(get_training_service)) -> None:
    try: service.delete_many(request.model_ids)
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
