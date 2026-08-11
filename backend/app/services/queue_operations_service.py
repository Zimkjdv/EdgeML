from __future__ import annotations

from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.domain.training_queue import TrainingQueueOperations
from app.domain.training_schemas import DeadLetterJobSummary, QueueStatus, TrainingJob
from app.services.training_service import TrainingService


class QueueOperationsService:
    """Application service for inspecting and controlling training queue work."""

    def __init__(self, queue: TrainingQueueOperations, training: TrainingService, queue_name: str) -> None:
        self._queue = queue
        self._training = training
        self._queue_name = queue_name

    def status(self) -> QueueStatus:
        depths = self._queue.queue_depths()
        return QueueStatus(
            queue_name=self._queue_name,
            queued_count=depths.get("queued", 0),
            processing_count=depths.get("processing", 0),
            dead_letter_count=depths.get("dead_letter", 0),
            queued_job_ids=self._queue.list_queued(),
            processing_job_ids=self._queue.list_processing(),
        )

    def dead_letter_jobs(self) -> list[DeadLetterJobSummary]:
        summaries: list[DeadLetterJobSummary] = []
        for job_id in self._queue.list_dead_letter():
            try:
                job = self._training.get_job(job_id)
            except ModelNotFoundError:
                # A stale queue entry should not make the whole operations page fail.
                continue
            summaries.append(self._summary(job))
        return summaries

    def requeue_dead_letter(self, job_id: str) -> TrainingJob:
        job = self._training.get_job(job_id)
        if job.status != "failed":
            raise PredictionValidationError("Only failed training jobs can be requeued.")
        if not self._queue.requeue_dead_letter(job_id):
            raise ModelNotFoundError(f"Dead-letter job '{job_id}' was not found.")
        return self._training.requeue_failed_job(job_id)

    def cancel_queued(self, job_id: str) -> TrainingJob:
        job = self._training.get_job(job_id)
        if job.status != "queued":
            raise PredictionValidationError("Only queued training jobs can be cancelled.")
        if not self._queue.remove_queued(job_id):
            raise PredictionValidationError("Training job is already being processed or was removed.")
        try:
            return self._training.cancel_job(job_id)
        except Exception:
            # Do not lose a job if the persisted state cannot be updated.
            self._queue.enqueue(job_id)
            raise

    @staticmethod
    def _summary(job: TrainingJob) -> DeadLetterJobSummary:
        return DeadLetterJobSummary(
            job_id=job.id,
            status=job.status,
            attempt=job.attempt,
            message=job.message,
            error=job.error,
            queued_at=job.queued_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )
