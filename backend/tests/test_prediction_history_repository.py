from datetime import datetime, timezone

from app.domain.schemas import PredictionHistoryRecord
from app.infrastructure.file_prediction_history_repository import FilePredictionHistoryRepository


def test_file_repository_persists_history_in_reverse_chronological_order(tmp_path) -> None:
    history_file = tmp_path / "prediction_history.jsonl"
    repository = FilePredictionHistoryRepository(history_file)
    older = PredictionHistoryRecord(
        id="older",
        model_id="model-v1",
        model_name="Model",
        source_filename="older.csv",
        row_count=2,
        created_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
    )
    newer = PredictionHistoryRecord(
        id="newer",
        model_id="model-v1",
        model_name="Model",
        source_filename="newer.csv",
        row_count=3,
        created_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
    )

    repository.add(older)
    repository.add(newer)

    reloaded_repository = FilePredictionHistoryRepository(history_file)
    assert [record.id for record in reloaded_repository.list()] == ["newer", "older"]
