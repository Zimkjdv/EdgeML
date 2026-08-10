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
        try:
            service.run_job(job_id, worker_id=worker_id)
        except Exception as exc:
            logger.exception("Training worker failed to execute job", extra={"event": "training.worker.job_error", "job_id": job_id, "worker_id": worker_id})
            try:
                service.mark_job_failed(job_id, str(exc))
            except Exception:
                logger.exception("Unable to persist worker job failure", extra={"event": "training.worker.persist_error", "job_id": job_id, "worker_id": worker_id})
        finally:
            queue.acknowledge(job_id)


if __name__ == "__main__":
    run_worker()
