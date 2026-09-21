"""Real Redis/OS-lock tests. Point EDGEML_TEST_REDIS_URL at an isolated test Redis."""
import multiprocessing
import os
from pathlib import Path
from uuid import uuid4

import pytest
import redis
from app.infrastructure.redis_training_job_queue import RedisTrainingJobQueue


def _claim(url, name, root, pipe):
    queue = RedisTrainingJobQueue(url, name, Path(root))
    job = queue.consume(timeout=1)
    pipe.send(job)
    pipe.recv()  # Parent deliberately terminates this process to test crash recovery.


@pytest.fixture
def real_queue(tmp_path):
    url = os.environ.get('EDGEML_TEST_REDIS_URL')
    if not url:
        pytest.skip('Set EDGEML_TEST_REDIS_URL for isolated real-Redis integration tests')
    client = redis.Redis.from_url(url, decode_responses=True)
    client.ping()
    name = 'edgeml-test-' + uuid4().hex
    queue = RedisTrainingJobQueue(url, name, tmp_path)
    yield queue, url, name, tmp_path
    for job in list(queue._owned):
        queue.release(job)
    keys = list(client.scan_iter(name + '*'))
    if keys:
        client.delete(*keys)


def test_live_owner_is_not_recovered_and_crash_is_recovered(real_queue):
    queue, url, name, root = real_queue
    queue.enqueue('job')
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe()
    process = context.Process(target=_claim, args=(url, name, str(root), child))
    process.start()
    try:
        assert parent.poll(30)
        assert parent.recv() == 'job'
        assert queue.recover_processing() == 0  # New replica cannot steal live work.
        assert queue.consume(timeout=0) is None
        process.terminate()
        process.join(10)
        assert not process.is_alive()
        assert queue.recover_processing() == 1
        assert queue.recover_processing() == 0
        assert queue.consume(timeout=1) == 'job'
        queue.acknowledge('job')
        assert queue.list_processing() == []
    finally:
        if process.is_alive():
            process.terminate(); process.join(10)
        parent.close(); child.close()


def test_retry_is_not_lost_while_original_owner_is_acknowledging(real_queue):
    first, url, name, root = real_queue
    second = RedisTrainingJobQueue(url, name, root)
    first.enqueue('job')
    assert first.consume(timeout=1) == 'job'
    first.enqueue('job')
    assert second.consume(timeout=0) is None
    assert first.list_queued() == ['job']
    first.acknowledge('job')
    assert second.consume(timeout=1) == 'job'
    second.acknowledge('job')
    assert second.queue_depths() == {'queued':0, 'processing':0, 'dead_letter':0}
