from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.dependencies import get_training_job_queue, get_training_service
from app.domain.training_schemas import TrainingJob
from app.domain.training_schemas import TrainingRequest
from app.main import create_app
from app.services.training_service import TrainingService


class RecordingQueue:
    def __init__(self, error: Exception | None = None) -> None:
        self.job_ids: list[str] = []
        self.error = error

    def enqueue(self, job_id: str) -> None:
        if self.error:
            raise self.error
        self.job_ids.append(job_id)


class FakeTrainingService:
    def __init__(self) -> None:
        self.failed: list[tuple[str, str]] = []

    def create_job(self, request) -> TrainingJob:
        return TrainingJob(
            id="job-1",
            status="queued",
            progress=0,
            message="queued",
            queued_at=datetime.now(timezone.utc),
        )

    def mark_job_failed(self, job_id: str, error: str) -> TrainingJob:
        self.failed.append((job_id, error))
        return TrainingJob(id=job_id, status="failed", progress=0, message="failed", error=error)


def request_payload() -> dict[str, object]:
    return {
        "dataset_id": "dataset-1",
        "model_name": "Queue Test",
        "target_column": "target",
        "feature_columns": ["feature"],
        "algorithm": "random_forest",
    }


def test_training_job_is_enqueued_without_background_tasks() -> None:
    service = FakeTrainingService()
    queue = RecordingQueue()
    app = create_app()
    app.dependency_overrides[get_training_service] = lambda: service
    app.dependency_overrides[get_training_job_queue] = lambda: queue

    response = TestClient(app).post("/api/training/jobs", json=request_payload())

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert queue.job_ids == ["job-1"]


def test_training_job_reports_queue_unavailable() -> None:
    service = FakeTrainingService()
    queue = RecordingQueue(RuntimeError("redis unavailable"))
    app = create_app()
    app.dependency_overrides[get_training_service] = lambda: service
    app.dependency_overrides[get_training_job_queue] = lambda: queue

    response = TestClient(app).post("/api/training/jobs", json=request_payload())

    assert response.status_code == 503
    assert service.failed == [("job-1", "redis unavailable")]


def test_training_job_lifecycle_metadata_is_json_serializable(tmp_path) -> None:
    service = TrainingService(None, tmp_path / "trained", tmp_path / "models", jobs_root=tmp_path / "jobs")
    request = TrainingRequest.model_validate(request_payload())

    job = service.create_job(request)
    loaded = service.get_job(job.id)

    assert loaded.status == "queued"
    assert loaded.queued_at is not None
