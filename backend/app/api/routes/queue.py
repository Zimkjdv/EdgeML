from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_queue_operations_service
from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.domain.training_schemas import DeadLetterJobSummary, QueueStatus, TrainingJob
from app.services.queue_operations_service import QueueOperationsService

router = APIRouter()


@router.get("/queue/status", response_model=QueueStatus)
def queue_status(service: QueueOperationsService = Depends(get_queue_operations_service)) -> QueueStatus:
    try:
        return service.status()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Training queue is unavailable.") from exc


@router.get("/queue/dead-letter", response_model=list[DeadLetterJobSummary])
def dead_letter_jobs(service: QueueOperationsService = Depends(get_queue_operations_service)) -> list[DeadLetterJobSummary]:
    try:
        return service.dead_letter_jobs()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Training queue is unavailable.") from exc


@router.post("/queue/dead-letter/{job_id}/requeue", response_model=TrainingJob)
def requeue_dead_letter(job_id: str, service: QueueOperationsService = Depends(get_queue_operations_service)) -> TrainingJob:
    try:
        return service.requeue_dead_letter(job_id)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PredictionValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Training queue is unavailable.") from exc


@router.post("/training/jobs/{job_id}/cancel", response_model=TrainingJob)
def cancel_training_job(job_id: str, service: QueueOperationsService = Depends(get_queue_operations_service)) -> TrainingJob:
    try:
        return service.cancel_queued(job_id)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PredictionValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Training queue is unavailable.") from exc
