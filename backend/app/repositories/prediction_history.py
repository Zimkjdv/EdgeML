from typing import Protocol

from app.domain.schemas import PredictionHistoryRecord


class PredictionHistoryRepository(Protocol):
    def add(self, record: PredictionHistoryRecord) -> None:
        ...

    def list(self) -> list[PredictionHistoryRecord]:
        ...
