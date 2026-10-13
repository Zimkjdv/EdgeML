"""Opt-in Worker lifecycle tests; only disposable Redis/storage may be used."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from uuid import uuid4

import pytest

from app.infrastructure.redis_training_job_queue import RedisTrainingJobQueue
from test_training_output_recovery import service, setup_job

URL = os.getenv('EDGEML_TEST_REDIS_URL')
SCENARIO = os.getenv('EDGEML_TEST_WORKER_SCENARIO_ROOT')
pytestmark = pytest.mark.skipif(not URL or os.name != 'posix', reason='requires disposable Redis and Linux worker signals')


def worker(root, name):
    env = dict(os.environ)
    env.pop('EDGEML_BUNDLED_MODELS_ROOT', None)
    for key, suffix in [('DATASETS_ROOT', 'datasets'), ('TRAINED_MODELS_ROOT', 'trained'),
                        ('TRAINING_JOBS_ROOT', 'jobs'), ('MODELS_ROOT', 'models'),
                        ('MODEL_REGISTRY_FILE', 'registry.json'), ('API_TOKENS_DATABASE', 'tokens.sqlite3')]:
        env['EDGEML_' + key] = str(root / suffix)
    env.update(EDGEML_REDIS_URL=URL, EDGEML_TRAINING_QUEUE_NAME=name,
               EDGEML_TRAINING_RETRY_BACKOFF_SECONDS='0', EDGEML_TRAINING_RETRY_BACKOFF_MAX_SECONDS='0')
    script = ('import time; from app.services.training_service import TrainingService; '
              'from app.workers.training_worker import run_worker; original=TrainingService._pipeline; '
              'TrainingService._pipeline=lambda self,*args: (time.sleep(1), original(*args))[1]; run_worker()')
    return subprocess.Popen([sys.executable, '-c', script], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def wait_status(training, job_id, status):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        current = training.get_job(job_id)
        if current.status == status: return current
        if current.status == 'failed': pytest.fail(current.error)
        time.sleep(.05)
    pytest.fail(f'Job did not reach {status}')


def exercise(root, name, job_id, stop_during_fit=False):
    training = service(root)
    process = worker(root, name)
    try:
        if stop_during_fit:
            wait_status(training, job_id, 'running')
            process.send_signal(signal.SIGTERM)
        complete = wait_status(training, job_id, 'completed')
        if not stop_during_fit: process.send_signal(signal.SIGTERM)
        output = process.communicate(timeout=20)[0].decode(errors='replace')
        assert process.returncode == 0, output[-2000:]
        assert len(training.list()) == 1
        assert complete.result_model_id == complete.output_model_id
        queue = RedisTrainingJobQueue(URL, name, root / 'jobs' / '.locks')
        assert queue.list_processing() == []
        return queue
    finally:
        if process.poll() is None: process.kill(); process.communicate()


def test_sigterm_finishes_current_job_and_acknowledges(tmp_path):
    training, job = setup_job(tmp_path)
    name = 'edge-worker-test-' + uuid4().hex
    queue = RedisTrainingJobQueue(URL, name, tmp_path / 'jobs' / '.locks')
    try:
        queue.enqueue(job.id); training.confirm_dispatch(job.id)
        exercise(tmp_path, name, job.id, stop_during_fit=True)
    finally:
        keys = list(queue._client.scan_iter(name + '*'))
        if keys: queue._client.delete(*keys)


def test_confirmed_queue_loss_is_reconciled_on_worker_start(tmp_path):
    training, job = setup_job(tmp_path)
    name = 'edge-worker-test-' + uuid4().hex
    queue = RedisTrainingJobQueue(URL, name, tmp_path / 'jobs' / '.locks')
    try:
        queue.enqueue(job.id); training.confirm_dispatch(job.id)
        queue._client.delete(queue._queue_key)
        exercise(tmp_path, name, job.id)
    finally:
        keys = list(queue._client.scan_iter(name + '*'))
        if keys: queue._client.delete(*keys)


@pytest.mark.skipif(not SCENARIO, reason='requires prepared storage and an actual disposable Redis restart')
def test_actual_redis_restart_recovers_confirmed_job():
    root = Path(SCENARIO)
    scenario = json.loads((root / 'scenario.json').read_text())
    queue = exercise(root, scenario['queue'], scenario['job'])
    keys = list(queue._client.scan_iter(scenario['queue'] + '*'))
    if keys: queue._client.delete(*keys)


if __name__ == '__main__':
    assert URL and SCENARIO, 'Only a disposable test scenario may be prepared.'
    root = Path(SCENARIO); root.mkdir(parents=True, exist_ok=True)
    training, job = setup_job(root)
    name = 'edge-worker-test-' + uuid4().hex
    queue = RedisTrainingJobQueue(URL, name, root / 'jobs' / '.locks')
    queue.enqueue(job.id); training.confirm_dispatch(job.id)
    queue._client.delete(queue._queue_key)  # Model the confirmed-ID loss window.
    (root / 'scenario.json').write_text(json.dumps({'job': job.id, 'queue': name}))
    print('Disposable queued job prepared for actual Redis restart.')
