import asyncio
from threading import Event

import httpx
import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_training_service
from app.core.config import get_settings
from app.domain.training_schemas import ExternalEvaluationResult
from app.main import create_app
from app.services.regression_metrics import regression_metrics
from test_training_algorithms import make_service
from test_training_data import request


def setup_model(tmp_path, imputer='median', published=False):
    datasets, service = make_service(tmp_path)
    train = pd.DataFrame({'數值': range(12), '類別': ['甲', '乙'] * 6, '目標': np.arange(12) * 2.})
    dataset = datasets.upload('training.csv', train.to_csv(index=False).encode())
    model = service.train(request(dataset.id, numeric_imputer=imputer))
    if published: model = service.publish(model.id)
    app = create_app()
    app.dependency_overrides[get_training_service] = lambda: service
    return datasets, service, model, TestClient(app)


@pytest.mark.parametrize('imputer', ['median', 'drop'])
@pytest.mark.parametrize('published', [False, True])
def test_csv_evaluation_persists_metrics_counts_without_retraining_or_dataset_upload(tmp_path, imputer, published):
    datasets, service, model, client = setup_model(tmp_path, imputer, published)
    frame = pd.DataFrame({'數值': range(12), '類別': ['甲', '乙'] * 6,
        '目標': np.arange(12) * 2., '額外欄位': [None] * 12})
    frame.loc[1, '數值'] = np.nan
    frame.loc[2, '類別'] = None
    frame.loc[3, '目標'] = np.nan
    root = tmp_path / 'trained' / model.id
    artifact = (root / 'model.pkl').read_bytes()
    dataset_ids = [item.id for item in datasets.list()]
    response = client.post(f'/api/trained-models/{model.id}/evaluate-csv',
        files={'file': ('中文測試.csv', frame.to_csv(index=False).encode('utf-8-sig'), 'text/csv')})
    assert response.status_code == 200, response.text
    result = response.json()
    cleaned = frame.dropna(subset=['目標'] + (['數值', '類別'] if imputer == 'drop' else []))
    pipeline = joblib.load(root / 'model.pkl')
    expected = regression_metrics(cleaned['目標'], pipeline.predict(cleaned[['數值', '類別']]))
    assert result['metrics'] == expected
    context = result['context']
    assert context['source'] == 'csv' and context['source_name'] == '中文測試.csv'
    assert context['input_rows'] == 12
    assert context['evaluated_rows'] == (11 if imputer == 'median' else 9)
    assert context['dropped_rows'] == 12 - context['evaluated_rows']
    reloaded = service.get(model.id)
    assert reloaded.test_metrics == expected
    assert reloaded.test_evaluation.model_dump(mode='json') == context
    assert reloaded.validation_metrics == model.validation_metrics
    assert reloaded.status == model.status
    assert (root / 'model.pkl').read_bytes() == artifact
    assert [item.id for item in datasets.list()] == dataset_ids
    summary = next(item for item in client.get('/api/trained-models').json() if item['id'] == model.id)
    assert summary['test_r2'] == expected['r2'] and summary['test_rmse'] == expected['rmse']


@pytest.mark.parametrize('csv', ['數值,類別\n1,甲\n', '數值,類別,目標\n1,甲,\n',
    '數值,類別,目標\n1,甲,文字\n', '數值,類別,目標\n1,甲,2,extra\n'])
def test_invalid_csv_preserves_existing_evaluation(tmp_path, csv):
    datasets, service, model, client = setup_model(tmp_path)
    service.evaluate(model.id, datasets.list()[0].id)
    path = tmp_path / 'trained' / model.id / 'record.json'
    before = path.read_bytes()
    response = client.post(f'/api/trained-models/{model.id}/evaluate-csv', files={'file': ('invalid.csv', csv.encode(), 'text/csv')})
    assert response.status_code == 422
    assert path.read_bytes() == before


def test_file_limit_extension_and_unknown_model(tmp_path, monkeypatch):
    _, _, model, client = setup_model(tmp_path)
    assert client.post(f'/api/trained-models/{model.id}/evaluate-csv', files={'file': ('data.txt', b'a', 'text/plain')}).status_code == 400
    assert client.post('/api/trained-models/missing/evaluate-csv', files={'file': ('data.csv', b'x,y\n1,2\n', 'text/csv')}).status_code == 404
    monkeypatch.setenv('EDGEML_MAX_UPLOAD_BYTES', '10')
    get_settings.cache_clear()
    assert client.post(f'/api/trained-models/{model.id}/evaluate-csv', files={'file': ('large.csv', b'x' * 11, 'text/csv')}).status_code == 400


def test_existing_dataset_evaluation_returns_saved_provenance(tmp_path):
    datasets, service, model, client = setup_model(tmp_path)
    dataset = datasets.list()[0]
    response = client.post(f'/api/trained-models/{model.id}/evaluate', json={'dataset_id': dataset.id})
    assert response.status_code == 200
    context = response.json()['context']
    assert context['source'] == 'dataset' and context['dataset_id'] == dataset.id
    assert context['source_name'] == dataset.name
    assert context['evaluated_rows'] == 12
    assert service.get(model.id).test_evaluation.source == 'dataset'


def test_csv_evaluation_requires_authentication_and_browser_csrf(tmp_path, monkeypatch):
    _, _, model, client = setup_model(tmp_path)
    monkeypatch.setenv('EDGEML_ANONYMOUS_API', 'false')
    monkeypatch.setenv('EDGEML_WEB_PASSWORD', 'test-evaluation-password')
    get_settings.cache_clear()
    path = f'/api/trained-models/{model.id}/evaluate-csv'
    files = {'file': ('test.csv', '數值,類別,目標\n1,甲,2\n2,乙,4\n'.encode(), 'text/csv')}
    assert client.post(path, files=files).status_code == 401
    login = client.post('/api/auth/session', headers={'X-EdgeML-Login': '1'},
        json={'username': 'admin', 'password': 'test-evaluation-password'})
    assert login.status_code == 200
    assert client.post(path, files=files).status_code == 403
    assert client.post(path, files=files, headers={'X-CSRF-Token': login.json()['csrf_token']}).status_code == 200


def test_csv_evaluation_does_not_block_health_requests():
    started, release = Event(), Event()

    class SlowTrainingService:
        def evaluate_csv(self, model_id, content, filename):
            started.set()
            assert release.wait(5), 'evaluation was not released'
            return ExternalEvaluationResult(metrics={'rmse': 0.2})

    async def exercise():
        app = create_app()
        app.dependency_overrides[get_training_service] = SlowTrainingService
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            evaluation = asyncio.create_task(client.post('/api/trained-models/test/evaluate-csv',
                files={'file': ('test.csv', b'x,y\n1,2\n', 'text/csv')}))
            try:
                assert await asyncio.to_thread(started.wait, 2)
                assert not evaluation.done()
                response = await asyncio.wait_for(client.get('/health/live'), timeout=1)
                assert response.status_code == 200 and not evaluation.done()
            finally:
                release.set()
                response = await evaluation
            assert response.status_code == 200 and response.json()['metrics']['rmse'] == 0.2
    asyncio.run(exercise())
