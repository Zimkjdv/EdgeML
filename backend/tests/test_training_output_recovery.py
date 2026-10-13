import json
import multiprocessing
import os
from pathlib import Path

import pytest

from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.infrastructure.trained_model_catalog import TrainedModelCatalog
from app.services.dataset_service import DatasetService
from app.services.training_service import TrainingService
from test_training_data import request


def service(root):
    root = Path(root)
    return TrainingService(DatasetService(root / 'datasets'), root / 'trained', root / 'models', root / 'jobs')


def setup_job(root):
    training = service(root)
    data = training._datasets.upload('input.csv', '數值,類別,目標\n1,甲,2\n2,乙,4\n3,甲,6\n4,乙,8\n'.encode())
    return training, training.create_job(request(data.id))


def _crash_attempt(root, job_id, phase):
    import app.services.training_service as module
    training = service(root)
    original_dump, original_write, original_rename = module.joblib.dump, module.write_json_atomic, Path.rename
    def dump(*args, **kwargs):
        result = original_dump(*args, **kwargs)
        if phase == 'artifact': os._exit(57)
        return result
    def write(path, payload):
        original_write(path, payload)
        if phase == 'record' and path.name == 'record.json': os._exit(57)
        if phase == 'completed' and path.parent.name == 'jobs' and payload.get('job', {}).get('status') == 'completed': os._exit(57)
    def rename(path, destination):
        result = original_rename(path, destination)
        if phase == 'published' and path.name.startswith('.staging-'): os._exit(57)
        return result
    module.joblib.dump, module.write_json_atomic, Path.rename = dump, write, rename
    training.run_job(job_id, 'crashing-worker')


@pytest.mark.parametrize('phase', ['artifact', 'record', 'published', 'completed'])
def test_process_crash_recovers_one_visible_model_and_stable_id(tmp_path, phase, monkeypatch):
    training, job = setup_job(tmp_path)
    process = multiprocessing.get_context('spawn').Process(target=_crash_attempt, args=(str(tmp_path), job.id, phase))
    process.start(); process.join(30)
    assert not process.is_alive() and process.exitcode == 57
    interrupted = training.get_job(job.id)
    reserved = interrupted.output_model_id
    assert reserved
    if phase in {'artifact', 'record'}:
        assert training.list() == [] and TrainedModelCatalog(tmp_path / 'trained').list() == []
        stage = next((tmp_path / 'trained').glob('.staging-*'))
        with pytest.raises(ModelNotFoundError): training.get(stage.name)
        with pytest.raises(ModelNotFoundError): TrainedModelCatalog(tmp_path / 'trained').get(stage.name)
    else:
        before = (tmp_path / 'trained' / reserved / 'model.pkl').read_bytes()
        def no_fit(*args, **kwargs): pytest.fail('Committed outputs must not be fitted again.')
        monkeypatch.setattr(training, 'train', no_fit)
    completed = training.run_job(job.id, 'recovering-worker')
    assert completed.status == 'completed' and completed.result_model_id == reserved
    assert len(training.list()) == 1
    if phase in {'published', 'completed'}:
        assert (tmp_path / 'trained' / reserved / 'model.pkl').read_bytes() == before
        assert completed.attempt == interrupted.attempt
    assert training.run_job(job.id).result_model_id == reserved
    if phase in {'artifact', 'record'}: assert list((tmp_path / 'trained').glob('.abandoned-*'))


def test_job_completion_write_failure_reuses_verified_artifact(tmp_path, monkeypatch):
    training, job = setup_job(tmp_path)
    original = training._write_job
    def fail(current, req):
        if current.status == 'completed': raise OSError('lost completion storage')
        return original(current, req)
    with monkeypatch.context() as patch:
        patch.setattr(training, '_write_job', fail)
        with pytest.raises(OSError): training.run_job(job.id)
    reserved = training.get_job(job.id).output_model_id
    assert training.has_committed_output(job.id)
    monkeypatch.setattr(training, 'train', lambda *a, **k: pytest.fail('must not retrain'))
    completed = training.run_job(job.id)
    assert completed.result_model_id == reserved and completed.attempt == 1


def test_changed_committed_artifact_is_not_overwritten_or_refitted(tmp_path, monkeypatch):
    training, job = setup_job(tmp_path)
    original = training._write_job
    def fail(current, req):
        if current.status == 'completed': raise OSError('simulated crash window')
        original(current, req)
    with monkeypatch.context() as patch:
        patch.setattr(training, '_write_job', fail)
        with pytest.raises(OSError): training.run_job(job.id)
    model_id = training.get_job(job.id).output_model_id
    path = tmp_path / 'trained' / model_id / 'model.pkl'
    path.write_bytes(b'operator-modified artifact')
    monkeypatch.setattr(training, 'train', lambda *a, **k: pytest.fail('must not overwrite'))
    with pytest.raises(PredictionValidationError, match='verification failed'): training.run_job(job.id)
    assert path.read_bytes() == b'operator-modified artifact'


def test_output_confirmation_can_retry_at_fit_limit_without_another_fit(tmp_path, monkeypatch):
    training, job = setup_job(tmp_path)
    original = training._write_job
    def fail(current, req):
        if current.status == 'completed': raise OSError('completion not saved')
        original(current, req)
    with monkeypatch.context() as patch:
        patch.setattr(training, '_write_job', fail)
        with pytest.raises(OSError): training.run_job(job.id)
    current, req = training._read_job(job.id)
    current.status, current.attempt = 'failed', 3
    training._write_job(current, req)
    training.schedule_retry(job.id, 3, committed_output=True)
    monkeypatch.setattr(training, 'train', lambda *a, **k: pytest.fail('no additional fit allowed'))
    completed = training.run_job(job.id)
    assert completed.status == 'completed' and completed.attempt == 3
