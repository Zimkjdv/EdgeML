import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

from app.api.dependencies import get_prediction_service
from app.domain.errors import PredictionValidationError
from app.domain.schemas import ModelManifest
from app.infrastructure.file_model_registry import FileModelRegistry
from app.infrastructure.model_catalog import FileModelCatalog
from app.infrastructure.predictor_factory import PredictorFactory
from app.main import create_app
from app.services.prediction_service import PredictionService
from test_api import InMemoryPredictionHistoryRepository


def expected_metrics(actual, predictions):
    return {'accuracy': round(float(accuracy_score(actual, predictions)), 6),
            'precision': round(float(precision_score(actual, predictions, average='weighted', zero_division=0)), 6),
            'recall': round(float(recall_score(actual, predictions, average='weighted', zero_division=0)), 6),
            'f1': round(float(f1_score(actual, predictions, average='weighted', zero_division=0)), 6)}


@pytest.mark.parametrize('package', ['CreditRisk', 'CustomerChurn'])
@pytest.mark.parametrize('transport', ['csv', 'json'])
@pytest.mark.parametrize('catalog_type', ['folders', 'registry'])
def test_bundled_binary_models_score_classification_without_editing_legacy_files(tmp_path, package, transport, catalog_type):
    source = Path(__file__).resolve().parents[1] / 'ml_models' / package
    folder = tmp_path / 'models' / package
    shutil.copytree(source, folder)
    before = (folder / 'metadata.json').read_bytes()
    manifest = FileModelCatalog(tmp_path / 'models').list()[0]
    assert manifest.problem_type == 'classification'
    catalog = (FileModelCatalog(tmp_path / 'models') if catalog_type == 'folders' else
               FileModelRegistry(tmp_path / 'registry.json', tmp_path / 'models'))
    manifest = catalog.get(manifest.id)
    sample_name = 'credit_risk_input.csv' if package == 'CreditRisk' else 'customer_churn_input.csv'
    frame = pd.read_csv(source.parents[1] / 'sample_data' / sample_name)
    predictions = PredictorFactory().create(manifest).predict(frame)
    truth = np.asarray(predictions).copy()
    truth[0] = 1 - truth[0]  # Include a real error so we don't only test perfect scores.
    frame[manifest.target] = truth
    frame.loc[1, manifest.features[0].name] = np.nan
    kept = frame.dropna(subset=[f.name for f in manifest.features])
    expected = expected_metrics(kept[manifest.target], np.asarray(predictions)[kept.index])
    history = InMemoryPredictionHistoryRepository()
    service = PredictionService(catalog, PredictorFactory(), history)
    app = create_app()
    app.dependency_overrides[get_prediction_service] = lambda: service
    with TestClient(app) as client:
        if transport == 'csv':
            response = client.post('/api/predict', data={'model_id': manifest.id},
                files={'file': ('input.csv', frame.to_csv(index=False).encode(), 'text/csv')})
            metrics = json.loads(response.headers.get('X-Prediction-Metrics', '{}'))
            assert 'prediction_correct' in response.text and 'prediction_error' not in response.text
            assert response.headers['X-Prediction-Dropped-Rows'] == '1'
        else:
            records = frame.astype(object).where(pd.notna(frame), None).to_dict(orient='records')
            response = client.post('/api/predict/json', json={'model_id': manifest.id, 'data': records})
            metrics = response.json().get('metrics')
            assert response.json()['dropped_rows'] == 1
            assert sum(not row['prediction_correct'] for row in response.json()['records']) == 1
        assert response.status_code == 200, response.text
        assert metrics == expected
        assert set(metrics) == {'accuracy', 'precision', 'recall', 'f1'}
    assert len(history.records) == 1
    assert (folder / 'metadata.json').read_bytes() == before


@pytest.mark.parametrize('kind', ['classification', 'binary_classification', 'multiclass_classification'])
@pytest.mark.parametrize('transport', ['csv', 'json'])
def test_chinese_text_labels_use_classification_metrics(tmp_path, kind, transport):
    manifest = ModelManifest(id='labels', name='中文分類', version='1', framework='sklearn',
        problem_type=kind, target='結果', features=[{'name': 'x', 'dtype': 'int64'}],
        author='test', created_at='2026-10-13', description='test', model_path=tmp_path)
    predictions = np.array(['合格', '不合格', '合格'])
    service = PredictionService(SimpleNamespace(get=lambda _: manifest),
        SimpleNamespace(create=lambda _: SimpleNamespace(predict=lambda _: predictions)),
        InMemoryPredictionHistoryRepository())
    app = create_app()
    app.dependency_overrides[get_prediction_service] = lambda: service
    with TestClient(app) as client:
        if transport == 'csv':
            response = client.post('/api/predict', data={'model_id': 'labels'},
                files={'file': ('labels.csv', 'x,結果\n1,合格\n2,合格\n3,不合格\n'.encode(), 'text/csv')})
            metrics = json.loads(response.headers['X-Prediction-Metrics'])
        else:
            response = client.post('/api/predict/json', json={'model_id': 'labels', 'data':
                [{'x': 1, '結果': '合格'}, {'x': 2, '結果': '合格'}, {'x': 3, '結果': '不合格'}]})
            metrics = response.json()['metrics']
    assert response.status_code == 200, response.text
    assert metrics == expected_metrics(['合格', '合格', '不合格'], predictions)


def test_unknown_type_is_rejected_at_manifest_and_evaluation_boundaries(tmp_path):
    payload = dict(id='unknown', name='unknown', version='1', framework='sklearn',
        problem_type='clustering', target='y', features=[], author='test',
        created_at='2026-10-13', description='test', model_path=tmp_path)
    with pytest.raises(ValidationError, match='Unsupported'):
        ModelManifest(**payload)
    with pytest.raises(PredictionValidationError, match='Unsupported'):
        PredictionService._evaluate_predictions('clustering', [1, 2], [1, 2])


@pytest.mark.parametrize('transport', ['csv', 'json'])
def test_invalid_manifest_returns_422_without_inference_or_history(tmp_path, transport):
    folder = tmp_path / 'models' / 'invalid'
    folder.mkdir(parents=True)
    (folder / 'metadata.json').write_text(json.dumps(dict(id='bad', name='bad', version='1',
        framework='sklearn', problem_type='clustering', target='y', features=[],
        author='test', created_at='2026-10-13', description='test')))
    history = InMemoryPredictionHistoryRepository()
    service = PredictionService(FileModelCatalog(tmp_path / 'models'), None, history)
    app = create_app()
    app.dependency_overrides[get_prediction_service] = lambda: service
    with TestClient(app) as client:
        response = (client.post('/api/predict/json', json={'model_id': 'bad', 'data': [{'x': 1}]})
                    if transport == 'json' else client.post('/api/predict', data={'model_id': 'bad'},
                    files={'file': ('input.csv', b'x\n1\n', 'text/csv')}))
    assert response.status_code == 422
    assert history.records == []


def test_incompatible_classification_truth_is_validation_error():
    with pytest.raises(PredictionValidationError, match='Ground Truth'):
        PredictionService._evaluate_predictions('classification', [0.5, 1.5], [0, 1])
