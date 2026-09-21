"""Real Redis/OS-lock tests. Point EDGEML_TEST_REDIS_URL at an isolated test Redis."""
import multiprocessing
import os
from pathlib import Path
from uuid import uuid4

import pytest
import redis
from app.infrastructure.redis_training_job_queue import RedisTrainingJobQueue
from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.domain.training_schemas import TrainingRequest
from app.services.queue_operations_service import QueueOperationsService
from app.services.training_service import TrainingService


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


def failed_job(real_queue):
    queue, _, name, root = real_queue
    training = TrainingService(None, root / 'trained', root / 'models', jobs_root=root / 'jobs')
    request = TrainingRequest(dataset_id='test', model_name='Replay test', target_column='y',
        feature_columns=['x'], algorithm='random_forest')
    job = training.create_job(request)
    training.mark_job_failed(job.id, 'original failure')
    queue.dead_letter(job.id)
    return training, QueueOperationsService(queue, training, name), job.id


@pytest.mark.parametrize('commit_before_error', [False, True])
def test_replay_survives_ambiguous_redis_error(real_queue, monkeypatch, commit_before_error):
    queue, _, _, _ = real_queue
    training, operations, job_id = failed_job(real_queue)
    original_eval = queue._client.eval

    def disconnect(*args):
        if commit_before_error:
            original_eval(*args)
        raise redis.ConnectionError('response lost')

    with monkeypatch.context() as patch:
        patch.setattr(queue._client, 'eval', disconnect)
        with pytest.raises(redis.ConnectionError):
            operations.requeue_dead_letter(job_id)
    assert training.get_job(job_id).status == 'queued'
    assert training.get_job(job_id).replay_pending
    if commit_before_error:
        assert queue.list_dead_letter() == []
        with pytest.raises(ModelNotFoundError):
            operations.requeue_dead_letter(job_id)
    else:
        assert queue.list_dead_letter() == [job_id]
        assert queue.list_queued() == []
        operations.requeue_dead_letter(job_id)
    assert queue.list_queued() == [job_id]
    assert queue.consume(timeout=0) == job_id
    assert training.get_job(job_id).status == 'queued'
    queue.acknowledge(job_id)


@pytest.mark.parametrize('failure_point', ['dump', 'replace'])
def test_replay_file_failure_preserves_original_and_can_retry(real_queue, monkeypatch, failure_point):
    queue, _, _, root = real_queue
    training, operations, job_id = failed_job(real_queue)
    path = root / 'jobs' / f'{job_id}.json'
    before = path.read_bytes()

    def fail(*args, **kwargs):
        raise OSError('injected storage failure')

    with monkeypatch.context() as patch:
        target = 'app.infrastructure.atomic_json.json.dump' if failure_point == 'dump' else 'app.infrastructure.atomic_json.os.replace'
        patch.setattr(target, fail)
        with pytest.raises(OSError):
            operations.requeue_dead_letter(job_id)
    assert path.read_bytes() == before
    assert training.get_job(job_id).status == 'failed'
    assert queue.list_dead_letter() == [job_id]
    assert queue.list_queued() == []
    assert list(path.parent.glob('*.tmp')) == []
    operations.requeue_dead_letter(job_id)
    assert queue.list_queued() == [job_id]


def _consume_persisted_status(url, name, root, pipe):
    root = Path(root)
    queue = RedisTrainingJobQueue(url, name, root)
    service = TrainingService(None, root / 'trained', root / 'models', jobs_root=root / 'jobs')
    pipe.send('ready')
    job_id = queue.consume(timeout=10)
    pipe.send(service.get_job(job_id).status if job_id else 'no job')
    if job_id:
        queue.acknowledge(job_id)


def test_replay_persists_ready_state_before_immediate_worker_claim(real_queue):
    queue, url, name, root = real_queue
    training, operations, job_id = failed_job(real_queue)
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe()
    worker = context.Process(target=_consume_persisted_status, args=(url, name, str(root), child))
    worker.start()
    try:
        assert parent.poll(30) and parent.recv() == 'ready'
        assert operations.requeue_dead_letter(job_id).status == 'queued'
        assert parent.poll(30) and parent.recv() == 'queued'
        worker.join(10)
        assert worker.exitcode == 0
        assert queue.queue_depths() == {'queued': 0, 'processing': 0, 'dead_letter': 0}
    finally:
        if worker.is_alive():
            worker.terminate()
            worker.join(10)
        parent.close()
        child.close()


def test_concurrent_replay_dispatches_only_once(real_queue):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    queue, url, name, root = real_queue
    training, first, job_id = failed_job(real_queue)
    second = QueueOperationsService(RedisTrainingJobQueue(url, name, root), training, name)
    barrier = Barrier(2)

    def replay(service):
        barrier.wait(timeout=5)
        try:
            return service.requeue_dead_letter(job_id).status
        except ModelNotFoundError:
            return 'already moved'

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(replay, [first, second]))
    assert sorted(results) == ['already moved', 'queued']
    assert queue.list_queued() == [job_id]


def test_replay_refuses_job_still_owned_by_worker(real_queue):
    queue, _, _, _ = real_queue
    training, operations, job_id = failed_job(real_queue)
    queue.enqueue(job_id)
    assert queue.consume(timeout=0) == job_id
    with pytest.raises(PredictionValidationError):
        operations.requeue_dead_letter(job_id)
    assert training.get_job(job_id).status == 'failed'
    queue.acknowledge(job_id)
    operations.requeue_dead_letter(job_id)
    assert queue.list_queued() == [job_id]


def test_lua_wrong_key_type_keeps_dead_letter_entry(real_queue):
    queue, _, _, _ = real_queue
    _, operations, job_id = failed_job(real_queue)
    queue._client.set(queue._queue_key, 'invalid key type')
    # Check the atomic transition independently; a Redis script runtime error
    # must not remove the source before discovering an invalid destination.
    from app.infrastructure.redis_training_job_queue import _REQUEUE_DEAD_SCRIPT
    with pytest.raises(redis.ResponseError):
        queue._client.eval(_REQUEUE_DEAD_SCRIPT, 2, queue._dead_letter_key, queue._queue_key, job_id)
    assert queue.list_dead_letter() == [job_id]


def _prepare_then_wait(url, name, root, job_id, pipe):
    root = Path(root)
    queue = RedisTrainingJobQueue(url, name, root)
    training = TrainingService(None, root / 'trained', root / 'models', jobs_root=root / 'jobs')

    def prepare():
        training.requeue_failed_job(job_id)
        pipe.send('persisted')
        pipe.recv()  # Simulate a crash between JSON commit and Redis dispatch.

    queue.requeue_dead_letter(job_id, prepare)


def test_replay_process_crash_after_preparation_can_be_resumed(real_queue):
    queue, url, name, root = real_queue
    training, operations, job_id = failed_job(real_queue)
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe()
    process = context.Process(target=_prepare_then_wait, args=(url, name, str(root), job_id, child))
    process.start()
    try:
        assert parent.poll(30) and parent.recv() == 'persisted'
        process.terminate()
        process.join(10)
        assert not process.is_alive()
        assert training.get_job(job_id).replay_pending
        assert queue.list_dead_letter() == [job_id]
        assert queue.list_queued() == []
        operations.requeue_dead_letter(job_id)
        assert queue.list_queued() == [job_id]
        assert queue.list_dead_letter() == []
    finally:
        if process.is_alive():
            process.terminate()
            process.join(10)
        parent.close()
        child.close()
