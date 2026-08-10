from __future__ import annotations

from typing import Protocol


class TrainingJobQueue(Protocol):
    """Application boundary for dispatching persisted training jobs."""

    def enqueue(self, job_id: str) -> None:
        ...


class TrainingJobConsumer(Protocol):
    """Worker-side boundary for consuming and acknowledging training jobs."""

    def consume(self, timeout: int = 5) -> str | None:
        ...

    def acknowledge(self, job_id: str) -> None:
        ...

    def recover_processing(self) -> int:
        ...
