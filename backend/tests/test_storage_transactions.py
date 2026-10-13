import json
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event

import pytest

from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.domain.schemas import PredictionHistoryRecord
from app.infrastructure.file_prediction_history_repository import FilePredictionHistoryRepository
from app.services.dataset_service import DatasetService
from app.services.training_service import TrainingService
from test_queue_operations import request
from test_api import client


def record(i):
    return PredictionHistoryRecord(id=str(i), model_id='model', model_name='中文',
        source_filename='input.csv', row_count=1, created_at=datetime(2026, 10, 13, tzinfo=timezone.utc) + timedelta(seconds=i))


def _append_many(root, start):
    for i in range(start, start + 12):
        FilePredictionHistoryRepository(Path(root) / 'history.jsonl').add(record(i))


def _datasets_many(root, prefix):
    service = DatasetService(Path(root))
    for i in range(4):
        data = service.upload('input.csv', b'x,y\n1,2\n')
        service.rename(data.id, f'{prefix}-{i}')


def _crash_upload(root, stage):
    import app.services.dataset_service as module
    original = module.write_json_atomic
    def write(path, payload):
        if path.suffix == '.json' and stage == 'csv': os._exit(57)
        original(path, payload)
        if path.suffix == '.json' and stage == 'metadata': os._exit(57)
    module.write_json_atomic = write
    DatasetService(Path(root)).upload('input.csv', b'x,y\n1,2\n')


def _crash_delete(root, dataset_id):
    original = Path.unlink
    def unlink(path, *args, **kwargs):
        original(path, *args, **kwargs)
        if path.name == f'{dataset_id}.json': os._exit(57)
    Path.unlink = unlink
    DatasetService(Path(root)).delete(dataset_id)


def test_cross_process_history_and_dataset_writes_do_not_lose_records(tmp_path):
    context = multiprocessing.get_context('spawn')
    with ProcessPoolExecutor(max_workers=2, mp_context=context) as pool:
        jobs = [pool.submit(_append_many, str(tmp_path), start) for start in (0, 12)]
        for job in jobs: job.result(timeout=60)
        jobs = [pool.submit(_datasets_many, str(tmp_path / 'datasets'), prefix) for prefix in ('a', 'b')]
        for job in jobs: job.result(timeout=60)
    assert len(FilePredictionHistoryRepository(tmp_path / 'history.jsonl').list()) == 24
    assert len(DatasetService(tmp_path / 'datasets').list()) == 8


@pytest.mark.parametrize('stage,visible', [('csv', 0), ('metadata', 1)])
def test_real_process_crash_recovers_upload_without_touching_unmarked_files(tmp_path, stage, visible):
    legacy = tmp_path / 'unrelated.csv'; legacy.write_bytes(b'keep')
    process = multiprocessing.get_context('spawn').Process(target=_crash_upload, args=(str(tmp_path), stage))
    process.start(); process.join(30)
    assert not process.is_alive() and process.exitcode == 57
    service = DatasetService(tmp_path)
    assert len(service.list()) == visible
    assert not list(tmp_path.glob('*.txn'))
    assert legacy.read_bytes() == b'keep'
    assert len(list(tmp_path.glob('*.json'))) == visible


def test_real_process_crash_completes_prepared_delete(tmp_path):
    service = DatasetService(tmp_path)
    data = service.upload('input.csv', b'x,y\n1,2\n')
    process = multiprocessing.get_context('spawn').Process(target=_crash_delete, args=(str(tmp_path), data.id))
    process.start(); process.join(30)
    assert not process.is_alive() and process.exitcode == 57
    assert DatasetService(tmp_path).list() == []
    assert not list(tmp_path.glob('*.csv')) and not list(tmp_path.glob('*.txn'))


def test_delete_waits_for_a_complete_frame_read(tmp_path, monkeypatch):
    first, second = DatasetService(tmp_path), DatasetService(tmp_path)
    data = first.upload('input.csv', b'x,y\n1,2\n')
    started, release = Event(), Event()
    original = first.read_csv
    def slow(content):
        started.set(); assert release.wait(5)
        return original(content)
    monkeypatch.setattr(first, 'read_csv', slow)
    with ThreadPoolExecutor(max_workers=2) as pool:
        read = pool.submit(first.frame, data.id)
        assert started.wait(5)
        delete = pool.submit(second.delete, data.id)
        try:
            with pytest.raises(TimeoutError): delete.result(timeout=.1)
        finally: release.set()
        assert len(read.result(timeout=5)) == 1
        delete.result(timeout=5)


def test_failed_atomic_rename_preserves_previous_metadata(tmp_path, monkeypatch):
    service = DatasetService(tmp_path)
    data = service.upload('input.csv', b'x\n1\n')
    path = tmp_path / f'{data.id}.json'; before = path.read_bytes()
    def fail(*args): raise OSError('injected atomic replace error')
    monkeypatch.setattr('app.infrastructure.atomic_json.os.replace', fail)
    with pytest.raises(OSError): service.rename(data.id, 'new name')
    assert path.read_bytes() == before


@pytest.mark.parametrize('broken', [b'{"id":', b'invalid\n', b'\xff\n'])
def test_history_corruption_is_repaired_with_original_bytes_archived(tmp_path, broken):
    path = tmp_path / 'history.jsonl'
    original = record(1).model_dump_json().encode() + b'\n' + broken
    path.write_bytes(original)
    repository = FilePredictionHistoryRepository(path)
    assert [r.id for r in repository.list()] == ['1']
    archives = list(tmp_path.glob('history.jsonl.recovery-*.jsonl'))
    assert len(archives) == 1 and archives[0].read_bytes() == original
    repository.add(record(2))
    assert [r.id for r in repository.list()] == ['2', '1']


def test_complete_tail_without_newline_survives_append(tmp_path):
    path = tmp_path / 'history.jsonl'
    path.write_bytes(record(1).model_dump_json().encode())
    repository = FilePredictionHistoryRepository(path)
    repository.add(record(2))
    assert [r.id for r in repository.list()] == ['2', '1']


def test_pagination_and_opt_in_retention_keep_archived_evidence(tmp_path):
    repository = FilePredictionHistoryRepository(tmp_path / 'history.jsonl', max_records=3)
    for i in range(5): repository.add(record(i))
    assert [r.id for r in repository.list(2, 1)] == ['3', '2']
    assert list(tmp_path.glob('history.jsonl.retention-*.jsonl'))
    path = tmp_path / 'all.jsonl'
    unlimited = FilePredictionHistoryRepository(path)
    for i in range(5): unlimited.add(record(i))
    assert len(unlimited.list()) == 5 and not list(tmp_path.glob('all.jsonl.retention-*'))


@pytest.mark.parametrize('transport', ['csv', 'json'])
def test_prediction_returns_503_if_audit_storage_fails(transport):
    class UnavailableHistory:
        def add(self, record): raise OSError('disk unavailable')
        def list(self, *args): return []
    test_client = client(UnavailableHistory())
    response = (test_client.post('/api/predict/json', json={'model_id': 'house-price-v1',
        'data': [{'Area': 80, 'Room': 2, 'Age': 15}]}) if transport == 'json' else
        test_client.post('/api/predict', data={'model_id': 'house-price-v1'},
            files={'file': ('input.csv', b'Area,Room,Age\n80,2,15\n', 'text/csv')}))
    assert response.status_code == 503 and 'audit storage' in response.json()['detail']


def test_job_start_cancel_race_and_stale_progress_preserve_state(tmp_path):
    service = TrainingService(None, tmp_path / 'trained', tmp_path / 'models', tmp_path / 'jobs')
    second = TrainingService(None, tmp_path / 'trained', tmp_path / 'models', tmp_path / 'jobs')
    job = service.create_job(request())
    def attempt(fn):
        try: return fn(job.id)
        except PredictionValidationError: return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, service.cancel_job), pool.submit(attempt, second._begin_job)]
        results = [f.result(timeout=5) for f in futures]
    current = service.get_job(job.id)
    assert current.status in {'running', 'cancelled'}
    assert sum(value is not None for value in results) == 1
    service._update_job(job, request(), 50, 'stale')
    assert service.get_job(job.id).status == current.status
    if current.status == 'running':
        second.mark_job_failed(job.id, 'lost enqueue response')
        assert service.get_job(job.id).status == 'running'


def test_history_api_pages_and_validates_bounds(tmp_path):
    repository = FilePredictionHistoryRepository(tmp_path / 'history.jsonl')
    for i in range(5): repository.add(record(i))
    test_client = client(repository)
    response = test_client.get('/api/prediction-history?limit=2&offset=1')
    assert [r['id'] for r in response.json()] == ['3', '2']
    assert test_client.get('/api/prediction-history?limit=0').status_code == 422


def test_durable_dispatch_marker_recovers_after_api_exit_or_lost_reply(tmp_path):
    service = TrainingService(None, tmp_path / 'trained', tmp_path / 'models', tmp_path / 'jobs')
    job = service.create_job(request())
    service.note_dispatch_failure(job.id, 'connection lost')
    class Queue:
        ids = set()
        def ensure_enqueued(self, job_id, eligible):
            if eligible(): self.ids.add(job_id)
    queue = Queue()
    fresh = TrainingService(None, tmp_path / 'trained', tmp_path / 'models', tmp_path / 'jobs')
    fresh.recover_pending_dispatch(queue)
    fresh.recover_pending_dispatch(queue)
    assert queue.ids == {job.id} and not list((tmp_path / 'jobs').glob('*.txn'))
    assert fresh.get_job(job.id).status == 'queued'
