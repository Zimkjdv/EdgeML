from typing import Protocol

from app.domain.schemas import PredictionHistoryRecord


class PredictionHistoryRepository(Protocol):
    def add(self, record: PredictionHistoryRecord) -> None:
        ...

    def list(self, limit: int = 100, offset: int = 0) -> list[PredictionHistoryRecord]:
        ...
