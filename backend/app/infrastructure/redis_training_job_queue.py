from __future__ import annotations

import redis


_RECOVER_PROCESSING_SCRIPT = """
local pending = redis.call('lrange', KEYS[1], 0, -1)
if #pending == 0 then
  return 0
end
for index = 1, #pending do
  redis.call('lpush', KEYS[2], pending[index])
end
redis.call('del', KEYS[1])
return #pending
"""


class RedisTrainingJobQueue:
    """At-least-once Redis queue for persisted training job identifiers."""

    def __init__(self, url: str, queue_name: str = "edgeml:training") -> None:
        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._queue_key = queue_name
        self._processing_key = f"{queue_name}:processing"
        self._dead_letter_key = f"{queue_name}:dead-letter"

    def enqueue(self, job_id: str) -> None:
        self._client.lpush(self._queue_key, job_id)

    def queue_depths(self) -> dict[str, int]:
        return {
            "queued": int(self._client.llen(self._queue_key)),
            "processing": int(self._client.llen(self._processing_key)),
            "dead_letter": int(self._client.llen(self._dead_letter_key)),
        }

    def list_queued(self) -> list[str]:
        return list(self._client.lrange(self._queue_key, 0, -1))

    def list_processing(self) -> list[str]:
        return list(self._client.lrange(self._processing_key, 0, -1))

    def list_dead_letter(self) -> list[str]:
        return list(self._client.lrange(self._dead_letter_key, 0, -1))

    def remove_queued(self, job_id: str) -> bool:
        return bool(self._client.lrem(self._queue_key, 1, job_id))

    def requeue_dead_letter(self, job_id: str) -> bool:
        removed = bool(self._client.lrem(self._dead_letter_key, 1, job_id))
        if not removed:
            return False
        try:
            self.enqueue(job_id)
        except Exception:
            # Preserve the dead-letter record if the primary queue is unavailable.
            self._client.lpush(self._dead_letter_key, job_id)
            raise
        return True

    def consume(self, timeout: int = 5) -> str | None:
        return self._client.brpoplpush(self._queue_key, self._processing_key, timeout=timeout)

    def acknowledge(self, job_id: str) -> None:
        self._client.lrem(self._processing_key, 1, job_id)

    def dead_letter(self, job_id: str) -> None:
        """Keep a terminally failed job ID for later inspection or replay."""

        self._client.lpush(self._dead_letter_key, job_id)

    def recover_processing(self) -> int:
        """Atomically requeue jobs left in processing after a worker restart.

        Worker replicas can start at the same time after a host restart. A
        Redis Lua script ensures only one worker moves and clears the pending
        list, preventing duplicate recovery and duplicate model artifacts.
        """

        recovered = self._client.eval(
            _RECOVER_PROCESSING_SCRIPT,
            2,
            self._processing_key,
            self._queue_key,
        )
        return int(recovered or 0)
