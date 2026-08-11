import signal
from threading import Event

from app.infrastructure.redis_training_job_queue import RedisTrainingJobQueue
from app.workers.training_worker import _install_signal_handlers, _is_retryable_error, _retry_delay


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

    def lrem(self, key: str, count: int, value: str) -> int:
        removed = 0
        values = self.lists.get(key, [])
        while value in values and (count == 0 or removed < count):
            values.remove(value)
            removed += 1
        return removed

    def llen(self, key: str) -> int:
        return len(self.lists.get(key, []))

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

    queue.enqueue("job-3")
    assert queue.consume(timeout=1) == "job-3"
    queue.dead_letter("job-3")
    queue.acknowledge("job-3")
    assert fake.lists["queue:dead-letter"] == ["job-3"]
    assert fake.lists["queue:processing"] == ["job-2"]


def test_queue_operations_report_and_move_jobs(monkeypatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr("redis.Redis.from_url", lambda *args, **kwargs: fake)
    queue = RedisTrainingJobQueue("redis://test", "queue")

    queue.enqueue("queued")
    queue.dead_letter("failed")
    assert queue.queue_depths() == {"queued": 1, "processing": 0, "dead_letter": 1}
    assert queue.list_dead_letter() == ["failed"]
    assert queue.requeue_dead_letter("failed")
    assert queue.list_dead_letter() == []
    assert queue.remove_queued("queued")
    assert queue.queue_depths() == {"queued": 1, "processing": 0, "dead_letter": 0}


def test_retry_policy_classifies_errors_and_caps_backoff() -> None:
    assert _is_retryable_error(OSError("temporary"))
    assert _is_retryable_error(TimeoutError("temporary"))
    assert not _is_retryable_error(ValueError("invalid training request"))
    assert _retry_delay(1, 2, 10) == 2
    assert _retry_delay(3, 2, 10) == 8
    assert _retry_delay(5, 2, 10) == 10


def test_worker_signal_handlers_request_stop(monkeypatch) -> None:
    registered: dict[signal.Signals, object] = {}
    monkeypatch.setattr(signal, "signal", lambda signum, handler: registered.__setitem__(signum, handler))
    stop_event = Event()

    _install_signal_handlers(stop_event)
    registered[signal.SIGTERM](signal.SIGTERM, None)

    assert stop_event.is_set()
    assert signal.SIGINT in registered
    assert signal.SIGTERM in registered
