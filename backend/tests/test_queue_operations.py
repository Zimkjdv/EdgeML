import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_queue_operations_service
from app.domain.errors import PredictionValidationError
from app.domain.training_schemas import QueueStatus, TrainingJob, TrainingRequest
from app.main import create_app
from app.services.queue_operations_service import QueueOperationsService
from app.services.training_service import TrainingService


class FakeOperationsQueue:
    def __init__(self) -> None:
        self.queued: list[str] = []
        self.processing: list[str] = []
        self.dead: list[str] = []

    def enqueue(self, job_id: str) -> None:
        self.queued.insert(0, job_id)

    def queue_depths(self) -> dict[str, int]:
        return {"queued": len(self.queued), "processing": len(self.processing), "dead_letter": len(self.dead)}

    def list_queued(self) -> list[str]:
        return list(self.queued)

    def list_processing(self) -> list[str]:
        return list(self.processing)

    def list_dead_letter(self) -> list[str]:
        return list(self.dead)

    def requeue_dead_letter(self, job_id: str) -> bool:
        if job_id not in self.dead:
            return False
        self.dead.remove(job_id)
        self.enqueue(job_id)
        return True

    def remove_queued(self, job_id: str) -> bool:
        if job_id not in self.queued:
            return False
        self.queued.remove(job_id)
        return True


def request() -> TrainingRequest:
    return TrainingRequest(
        dataset_id="dataset-1",
        model_name="Queue Operations Test",
        target_column="target",
        feature_columns=["feature"],
        algorithm="random_forest",
    )


def test_queue_operations_cancel_and_requeue(tmp_path) -> None:
    training = TrainingService(None, tmp_path / "trained", tmp_path / "models", jobs_root=tmp_path / "jobs")
    queue = FakeOperationsQueue()
    operations = QueueOperationsService(queue, training, "queue")

    queued = training.create_job(request())
    queue.enqueue(queued.id)
    cancelled = operations.cancel_queued(queued.id)
    assert cancelled.status == "cancelled"
    assert queue.queued == []

    failed = training.create_job(request())
    training.mark_job_failed(failed.id, "temporary failure")
    queue.dead.append(failed.id)
    replayed = operations.requeue_dead_letter(failed.id)
    assert replayed.status == "queued"
    assert replayed.attempt == 0
    assert queue.dead == []
    assert queue.queued == [failed.id]


def test_queue_operations_reject_non_queued_cancel(tmp_path) -> None:
    training = TrainingService(None, tmp_path / "trained", tmp_path / "models", jobs_root=tmp_path / "jobs")
    queue = FakeOperationsQueue()
    operations = QueueOperationsService(queue, training, "queue")
    failed = training.create_job(request())
    training.mark_job_failed(failed.id, "invalid request")

    with pytest.raises(PredictionValidationError):
        operations.cancel_queued(failed.id)


def test_dead_letter_summaries_include_failure_metadata(tmp_path) -> None:
    training = TrainingService(None, tmp_path / "trained", tmp_path / "models", jobs_root=tmp_path / "jobs")
    queue = FakeOperationsQueue()
    operations = QueueOperationsService(queue, training, "queue")
    failed = training.create_job(request())
    training.mark_job_failed(failed.id, "bad input")
    queue.dead.append(failed.id)

    summaries = operations.dead_letter_jobs()
    assert len(summaries) == 1
    assert summaries[0].job_id == failed.id
    assert summaries[0].status == "failed"
    assert summaries[0].error == "bad input"


class StubQueueOperationsService:
    def status(self) -> QueueStatus:
        return QueueStatus(queue_name="queue", queued_count=2, processing_count=1, dead_letter_count=3, queued_job_ids=["job-1"], processing_job_ids=["job-2"])

    def dead_letter_jobs(self):
        return []

    def requeue_dead_letter(self, job_id: str):
        return TrainingJob(id=job_id, status="queued", progress=0, message="requeued")

    def cancel_queued(self, job_id: str):
        return TrainingJob(id=job_id, status="cancelled", progress=0, message="cancelled")


def test_queue_operations_api_exposes_status_and_controls() -> None:
    app = create_app()
    app.dependency_overrides[get_queue_operations_service] = StubQueueOperationsService
    client = TestClient(app)

    status = client.get("/api/queue/status")
    assert status.status_code == 200
    assert status.json()["dead_letter_count"] == 3

    cancelled = client.post("/api/training/jobs/job-1/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    requeued = client.post("/api/queue/dead-letter/job-1/requeue")
    assert requeued.status_code == 200
    assert requeued.json()["status"] == "queued"
