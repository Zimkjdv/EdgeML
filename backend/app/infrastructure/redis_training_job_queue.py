from __future__ import annotations

import redis
import hashlib
import time
from pathlib import Path
from app.infrastructure.file_lock import FileLock


_RECOVER_PROCESSING_SCRIPT = """
local removed = redis.call('lrem', KEYS[1], 0, ARGV[1])
if removed > 0 then redis.call('lpush', KEYS[2], ARGV[1]) end
return removed > 0 and 1 or 0
"""


class RedisTrainingJobQueue:
    """At-least-once Redis queue for persisted training job identifiers."""

    def __init__(self, url: str, queue_name: str = "edgeml:training", locks_root: Path | None = None) -> None:
        self._client = redis.Redis.from_url(url, decode_responses=True)
        self._queue_key = queue_name
        self._processing_key = f"{queue_name}:processing"
        self._dead_letter_key = f"{queue_name}:dead-letter"
        if locks_root is None:
            from app.core.config import get_settings
            locks_root = get_settings().training_jobs_root / '.locks'
        self._locks_root = locks_root / hashlib.sha256(queue_name.encode()).hexdigest()
        self._guard = FileLock(self._locks_root / 'dispatch.lock')
        self._owned: dict[str, FileLock] = {}

    def _job_lock(self, job_id: str) -> FileLock:
        return FileLock(self._locks_root / (hashlib.sha256(job_id.encode()).hexdigest() + '.lock'), timeout=0)

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
        # One shared-volume guard closes the move-to-processing/ownership gap.
        # The job lock stays open for the entire training attempt and is released
        # by the OS even on an ungraceful process/container exit.
        deadline = time.monotonic() + timeout
        while True:
            with self._guard:
                job_id = self._client.rpoplpush(self._queue_key, self._processing_key)
                if job_id:
                    lock = self._job_lock(job_id)
                    try:
                        lock.__enter__()
                    except TimeoutError:
                        # A retry/duplicate may be queued before its owner acks.
                        self._client.lrem(self._processing_key, 1, job_id)
                        self._client.lpush(self._queue_key, job_id)
                    else:
                        self._owned[job_id] = lock
                        return job_id
            if time.monotonic() >= deadline:
                return None
            time.sleep(min(0.1, max(0, deadline - time.monotonic())))

    def acknowledge(self, job_id: str) -> None:
        with self._guard:
            lock = self._owned.pop(job_id, None)
            if lock:
                try:
                    self._client.lrem(self._processing_key, 1, job_id)
                finally:
                    lock.__exit__(None, None, None)

    def dead_letter(self, job_id: str) -> None:
        """Keep a terminally failed job ID for later inspection or replay."""

        self._client.lpush(self._dead_letter_key, job_id)

    def recover_processing(self) -> int:
        """Recover only unlocked jobs. All replicas must share locks_root.

        Supported on a single host/local Docker volume, not separate host disks
        or unverified network filesystems. Stop all legacy workers before upgrade.
        """
        recovered = 0
        with self._guard:
            for job_id in set(self.list_processing()):
                try:
                    with self._job_lock(job_id):
                        recovered += int(self._client.eval(_RECOVER_PROCESSING_SCRIPT, 2,
                            self._processing_key, self._queue_key, job_id) or 0)
                except TimeoutError:
                    continue
        return recovered

    def release(self, job_id: str) -> None:
        """Relinquish ownership while leaving processing durable for recovery."""
        lock = self._owned.pop(job_id, None)
        if lock:
            lock.__exit__(None, None, None)
