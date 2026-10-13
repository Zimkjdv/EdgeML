import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies import get_dataset_service, get_training_job_queue, get_training_service
from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.domain.training_schemas import ExternalEvaluationRequest, TrainingRequest
from app.main import create_app
from app.services.dataset_service import DatasetService


INVALID_IDS = ['../outside', '..\\outside', '/tmp/outside', 'C:\\outside',
               '.', '..', '', 'not-a-uuid', str(uuid4()).upper()]


@pytest.mark.parametrize('identifier', INVALID_IDS)
def test_dataset_paths_rejected_without_reading_or_mutating_outside(tmp_path, identifier):
    outside = DatasetService(tmp_path / 'outside')
    dataset = outside.upload('中文.csv', '數值,目標\n1,2\n'.encode())
    snapshots = {p: p.read_bytes() for p in (tmp_path / 'outside').iterdir()}
    service = DatasetService(tmp_path / 'inside')
    values = [identifier, f'../outside/{dataset.id}', f'..\\outside\\{dataset.id}']
    for value in values:
        for operation in (service.get, service.frame, service.delete,
                          lambda i: service.rename(i, '新名稱')):
            with pytest.raises(PredictionValidationError):
                operation(value)
    assert all(p.read_bytes() == before for p, before in snapshots.items())
    assert not list((tmp_path / 'inside').glob('*.csv'))
    assert not list((tmp_path / 'inside').glob('*.json'))


def test_canonical_id_still_supports_dataset_lifecycle_and_missing_404(tmp_path):
    service = DatasetService(tmp_path)
    dataset = service.upload('中文.csv', '數值,目標\n1,2\n'.encode())
    assert service.get(dataset.id).id == dataset.id
    assert service.frame(dataset.id).iloc[0].tolist() == [1, 2]
    assert service.rename(dataset.id, '新名稱').name == '新名稱'
    assert service.list()[0].name == '新名稱'
    service.delete(dataset.id)
    with pytest.raises(ModelNotFoundError):
        service.get(dataset.id)


@pytest.mark.parametrize('suffix', ['.json', '.csv'])
def test_dataset_symlinks_never_read_or_deleted(tmp_path, suffix):
    service = DatasetService(tmp_path / 'inside')
    dataset = service.upload('input.csv', b'x,y\n1,2\n')
    linked = tmp_path / 'inside' / f'{dataset.id}{suffix}'
    outside = tmp_path / f'outside{suffix}'
    before = linked.read_bytes()
    outside.write_bytes(before)
    linked.unlink()
    try:
        linked.symlink_to(outside)
    except OSError:
        pytest.skip('Creating symlinks requires privileges on this Windows host.')
    for operation in (service.get, service.frame, service.delete,
                      lambda i: service.rename(i, 'changed')):
        with pytest.raises(ModelNotFoundError):
            operation(dataset.id)
    assert service.list() == []
    assert outside.read_bytes() == before
    assert linked.is_symlink()
    assert (tmp_path / 'inside' / f'{dataset.id}.json').exists()
    assert (tmp_path / 'inside' / f'{dataset.id}.csv').exists()


def test_metadata_id_cannot_redirect_identity(tmp_path):
    service = DatasetService(tmp_path)
    dataset = service.upload('input.csv', b'x,y\n1,2\n')
    path = tmp_path / f'{dataset.id}.json'
    metadata = json.loads(path.read_text())
    metadata['id'] = str(uuid4())
    path.write_text(json.dumps(metadata))
    with pytest.raises(PredictionValidationError, match='does not match'):
        service.get(dataset.id)


@pytest.mark.parametrize('field', ['dataset_id', 'test_dataset_id'])
def test_training_and_evaluation_refs_reject_paths_before_dispatch(field):
    payload = dict(dataset_id=str(uuid4()), model_name='test', target_column='y',
                   feature_columns=['x'], algorithm='random_forest')
    payload[field] = '..\\outside'
    with pytest.raises(ValidationError):
        TrainingRequest(**payload)
    with pytest.raises(ValidationError):
        ExternalEvaluationRequest(dataset_id='../outside')


def test_http_encoded_windows_paths_and_body_refs_are_rejected(tmp_path):
    app = create_app()
    service = DatasetService(tmp_path / 'datasets')
    app.dependency_overrides[get_dataset_service] = lambda: service

    def no_training_service():
        raise AssertionError('Invalid references must be rejected before business operations.')

    # Dependencies are resolved before body validation, so use a service stub
    # whose methods must never be invoked instead of raising on construction.
    class NoTraining:
        def create_job(self, *args): no_training_service()
        def evaluate(self, *args): no_training_service()

    app.dependency_overrides[get_training_service] = NoTraining
    class NoQueue:
        def enqueue(self, *args): no_training_service()
    app.dependency_overrides[get_training_job_queue] = NoQueue
    with TestClient(app) as client:
        for method in ('get', 'patch', 'delete'):
            kwargs = {'json': {'name': 'new'}} if method == 'patch' else {}
            response = getattr(client, method)('/api/datasets/..%5Coutside', **kwargs)
            assert response.status_code == 422, response.text
        response = client.post('/api/trained-models/unused/evaluate', json={'dataset_id': '..\\outside'})
        assert response.status_code == 422
        for field in ('dataset_id', 'test_dataset_id'):
            payload = dict(dataset_id=str(uuid4()), model_name='test', target_column='y',
                           feature_columns=['x'], algorithm='random_forest')
            payload[field] = '..\\outside'
            response = client.post('/api/training/jobs', json=payload)
            assert response.status_code == 422
    assert not list(service._root.glob('*.csv'))
    assert not list(service._root.glob('*.json'))
