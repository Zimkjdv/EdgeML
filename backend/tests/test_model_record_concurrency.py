from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from app.domain.errors import ModelNotFoundError
from app.services.training_service import TrainingService
from test_training_data import request
from test_training_algorithms import make_service


@pytest.mark.parametrize('operation', ['rename', 'delete', 'publish'])
def test_evaluation_serializes_with_other_service_mutations(tmp_path, monkeypatch, operation):
    datasets, service = make_service(tmp_path)
    data = datasets.upload('train.csv', '數值,類別,目標\n1,甲,2\n2,乙,4\n3,甲,6\n4,乙,8\n'.encode())
    model = service.train(request(data.id))
    other = TrainingService(datasets, tmp_path / 'trained', tmp_path / 'models')
    evaluating, release, attempted = Event(), Event(), Event()
    original = service._metrics

    def slow_metrics(*args):
        evaluating.set()
        assert release.wait(5)
        return original(*args)
    monkeypatch.setattr(service, '_metrics', slow_metrics)

    def mutate():
        attempted.set()
        if operation == 'rename': return other.rename(model.id, '新名稱')
        if operation == 'publish': return other.publish(model.id)
        return other.delete_many([model.id])

    with ThreadPoolExecutor(max_workers=2) as pool:
        evaluation = pool.submit(service.evaluate, model.id, data.id)
        assert evaluating.wait(5)
        mutation = pool.submit(mutate)
        assert attempted.wait(5)
        try:
            with pytest.raises(TimeoutError): mutation.result(timeout=.1)
        finally:
            release.set()
        metrics = evaluation.result(timeout=5).metrics
        mutation.result(timeout=5)
    if operation == 'delete':
        with pytest.raises(ModelNotFoundError): service.get(model.id)
    else:
        record = service.get(model.id)
        assert record.test_metrics == metrics
        assert record.name == ('新名稱' if operation == 'rename' else model.name)
        assert record.status == ('published' if operation == 'publish' else 'draft')


def test_failed_atomic_replace_preserves_complete_record(tmp_path, monkeypatch):
    datasets, service = make_service(tmp_path)
    data = datasets.upload('train.csv', '數值,類別,目標\n1,甲,2\n2,乙,4\n3,甲,6\n4,乙,8\n'.encode())
    model = service.train(request(data.id))
    path = tmp_path / 'trained' / model.id / 'record.json'
    before = path.read_bytes()
    def fail(*args): raise OSError('injected replace failure')
    monkeypatch.setattr('app.infrastructure.atomic_json.os.replace', fail)
    with pytest.raises(OSError): service.evaluate(model.id, data.id)
    assert path.read_bytes() == before
    assert service.get(model.id).id == model.id
    assert not list(path.parent.glob('*.tmp'))
