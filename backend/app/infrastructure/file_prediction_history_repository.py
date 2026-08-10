import json
from pathlib import Path
from threading import Lock

from app.domain.schemas import PredictionHistoryRecord


class FilePredictionHistoryRepository:
    def __init__(self, history_file: Path) -> None:
        self._history_file = history_file
        self._lock = Lock()

    def add(self, record: PredictionHistoryRecord) -> None:
        self._history_file.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._history_file.open("a", encoding="utf-8") as file:
            file.write(record.model_dump_json() + "\n")

    def list(self) -> list[PredictionHistoryRecord]:
        if not self._history_file.exists():
            return []

        with self._lock, self._history_file.open(encoding="utf-8") as file:
            records = [
                PredictionHistoryRecord.model_validate(json.loads(line))
                for line in file
                if line.strip()
            ]
        return sorted(records, key=lambda record: record.created_at, reverse=True)
