from __future__ import annotations

import logging
import os
import socket
import time

import redis

from app.api.dependencies import get_training_service
from app.core.config import get_settings
from app.core.observability import configure_logging
from app.infrastructure.redis_training_job_queue import RedisTrainingJobQueue


logger = logging.getLogger("edgeml.training.worker")


def _is_retryable_error(error: Exception) -> bool:
    """Retry transient infrastructure failures, not deterministic training errors."""

    return isinstance(error, (OSError, TimeoutError, ConnectionError, redis.RedisError))


def _retry_delay(attempt: int, base_seconds: float, max_seconds: float) -> float:
    """Return bounded exponential backoff for the next attempt."""

    return min(base_seconds * (2 ** max(attempt - 1, 0)), max_seconds)


def run_worker() -> None:
    configure_logging()
    settings = get_settings()
    queue = RedisTrainingJobQueue(settings.redis_url, settings.training_queue_name)
    service = get_training_service()
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    recovered = queue.recover_processing()
    logger.info("Training worker started", extra={"event": "training.worker.started", "worker_id": worker_id})
    if recovered:
        logger.warning(
            "Recovered processing jobs",
            extra={"event": "training.worker.recovered", "job_id": f"count:{recovered}", "worker_id": worker_id},
        )

    while True:
        try:
            job_id = queue.consume(timeout=5)
        except redis.RedisError:
            logger.exception("Training queue connection failed", extra={"event": "training.worker.queue_error", "worker_id": worker_id})
            time.sleep(5)
            continue
        if not job_id:
            continue
        acknowledge = True
        try:
            service.run_job(job_id, worker_id=worker_id)
        except Exception as exc:
            logger.exception("Training worker failed to execute job", extra={"event": "training.worker.job_error", "job_id": job_id, "worker_id": worker_id})
            try:
                job = service.get_job(job_id)
                if _is_retryable_error(exc) and job.attempt < settings.training_max_attempts:
                    service.schedule_retry(job_id, settings.training_max_attempts)
                    delay = _retry_delay(job.attempt, settings.training_retry_backoff_seconds, settings.training_retry_backoff_max_seconds)
                    if delay:
                        time.sleep(delay)
                    queue.enqueue(job_id)
                    logger.warning(
                        "Training job scheduled for retry",
                        extra={"event": "training.worker.retry_scheduled", "job_id": job_id, "worker_id": worker_id},
                    )
                else:
                    logger.error(
                        "Training job reached a terminal failure",
                        extra={"event": "training.worker.job_terminal_failure", "job_id": job_id, "worker_id": worker_id},
                    )
            except Exception:
                acknowledge = False
                logger.exception("Unable to schedule training job retry", extra={"event": "training.worker.retry_error", "job_id": job_id, "worker_id": worker_id})
        finally:
            if acknowledge:
                queue.acknowledge(job_id)


if __name__ == "__main__":
    run_worker()
