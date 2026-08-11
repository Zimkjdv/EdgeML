from __future__ import annotations

from typing import Protocol


class TrainingJobQueue(Protocol):
    """Application boundary for dispatching persisted training jobs."""

    def enqueue(self, job_id: str) -> None:
        ...


class TrainingQueueOperations(Protocol):
    """Administrative operations exposed by the training queue boundary."""

    def queue_depths(self) -> dict[str, int]:
        ...

    def list_queued(self) -> list[str]:
        ...

    def list_processing(self) -> list[str]:
        ...

    def list_dead_letter(self) -> list[str]:
        ...

    def requeue_dead_letter(self, job_id: str) -> bool:
        ...

    def remove_queued(self, job_id: str) -> bool:
        ...


class TrainingJobConsumer(Protocol):
    """Worker-side boundary for consuming and acknowledging training jobs."""

    def consume(self, timeout: int = 5) -> str | None:
        ...

    def acknowledge(self, job_id: str) -> None:
        ...

    def dead_letter(self, job_id: str) -> None:
        ...

    def recover_processing(self) -> int:
        ...
