from __future__ import annotations

import redis


class RedisTrainingJobQueue:
    """At-least-once Redis queue for persisted training job identifiers."""

    def __init__(self, url: str, queue_name: str = "edgeml:training") -> None:
        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._queue_key = queue_name
        self._processing_key = f"{queue_name}:processing"
        self._dead_letter_key = f"{queue_name}:dead-letter"

    def enqueue(self, job_id: str) -> None:
        self._client.lpush(self._queue_key, job_id)

    def consume(self, timeout: int = 5) -> str | None:
        return self._client.brpoplpush(self._queue_key, self._processing_key, timeout=timeout)

    def acknowledge(self, job_id: str) -> None:
        self._client.lrem(self._processing_key, 1, job_id)

    def dead_letter(self, job_id: str) -> None:
        """Keep a terminally failed job ID for later inspection or replay."""

        self._client.lpush(self._dead_letter_key, job_id)

    def recover_processing(self) -> int:
        """Requeue jobs left in the processing list after a worker restart."""

        pending = self._client.lrange(self._processing_key, 0, -1)
        if not pending:
            return 0
        self._client.lpush(self._queue_key, *pending)
        self._client.delete(self._processing_key)
        return len(pending)
