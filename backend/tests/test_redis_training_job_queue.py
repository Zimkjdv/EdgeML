from app.infrastructure.redis_training_job_queue import RedisTrainingJobQueue
from app.workers.training_worker import _is_retryable_error, _retry_delay


class FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}

    def lpush(self, key: str, *values: str) -> None:
        self.lists.setdefault(key, [])
        self.lists[key][0:0] = list(values)

    def brpoplpush(self, source: str, destination: str, timeout: int) -> str | None:
        if not self.lists.get(source):
            return None
        value = self.lists[source].pop()
        self.lpush(destination, value)
        return value

    def lrem(self, key: str, count: int, value: str) -> None:
        if value in self.lists.get(key, []):
            self.lists[key].remove(value)

    def lrange(self, key: str, start: int, end: int) -> list[str]:
        return list(self.lists.get(key, []))

    def delete(self, key: str) -> None:
        self.lists.pop(key, None)


def test_redis_queue_dispatches_acknowledges_and_recovers(monkeypatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr("redis.Redis.from_url", lambda *args, **kwargs: fake)
    queue = RedisTrainingJobQueue("redis://test", "queue")

    queue.enqueue("job-1")
    assert queue.consume(timeout=1) == "job-1"
    queue.acknowledge("job-1")
    assert fake.lists["queue:processing"] == []

    queue.enqueue("job-2")
    assert queue.consume(timeout=1) == "job-2"
    assert queue.recover_processing() == 1
    assert queue.consume(timeout=1) == "job-2"


def test_retry_policy_classifies_errors_and_caps_backoff() -> None:
    assert _is_retryable_error(OSError("temporary"))
    assert _is_retryable_error(TimeoutError("temporary"))
    assert not _is_retryable_error(ValueError("invalid training request"))
    assert _retry_delay(1, 2, 10) == 2
    assert _retry_delay(3, 2, 10) == 8
    assert _retry_delay(5, 2, 10) == 10
