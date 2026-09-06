import csv
import io
import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_feature_importance_service
from app.core.config import get_settings
from app.domain.errors import ModelNotFoundError
from app.domain.training_schemas import TrainingRequest
from app.infrastructure.predictor_factory import PredictorFactory
from app.infrastructure.trained_model_catalog import TrainedModelCatalog
from app.main import create_app
from app.services.dataset_service import DatasetService
from app.services.feature_importance_service import FeatureImportanceService, calculate_importance
from app.services.training_service import TrainingService


def test_original_column_rankings_and_sampling_are_repeatable():
    frame = pd.DataFrame({'signal': np.arange(80), 'constant': np.ones(80), 'category': ['A', 'B'] * 40})
    predict = lambda x: x['signal'].to_numpy() * 2
    args = (predict, frame, frame.signal * 2, False, 'dataset', 'training')
    report = calculate_importance(*args, sample_limit=30)
    assert report['sample_count'] == 30
    assert report['rankings'][0]['feature'] == 'signal'
    assert report['rankings'][0]['importance'] > 0
    assert all(row['importance'] == 0 for row in report['rankings'][1:])
    assert report['rankings'] == calculate_importance(*args, sample_limit=30)['rankings']


def test_classification_and_negative_importance_are_not_clipped():
    frame = pd.DataFrame({'category': ['A', 'B'] * 40, 'constant': [0] * 80})
    report = calculate_importance(lambda x: x.category.to_numpy(), frame, frame.category, True, 'data', 'external_test')
    assert report['metric'] == 'accuracy_drop'
    assert report['rankings'][0]['feature'] == 'category'
    assert report['rankings'][0]['importance'] > 0
    numbers = pd.DataFrame({'signal': np.arange(-40, 40)})
    report = calculate_importance(lambda x: -x.signal.to_numpy(), numbers, numbers.signal, False, 'data', 'training')
    assert report['rankings'][0]['importance'] < 0


@pytest.fixture
def trained(tmp_path):
    datasets = DatasetService(tmp_path / 'datasets')
    frame = pd.DataFrame({'signal': np.arange(36), 'constant': [1] * 36, 'target': np.arange(36) * 2})
    data = datasets.upload('train.csv', frame.to_csv(index=False).encode())
    external = datasets.upload('test.csv', frame.iloc[:12].to_csv(index=False).encode())
    root = tmp_path / 'trained'
    training = TrainingService(datasets, root, tmp_path / 'published')
    model = training.train(TrainingRequest(dataset_id=data.id, test_dataset_id=external.id, model_name='importance test',
        target_column='target', feature_columns=['signal', 'constant'], algorithm='random_forest', cv_folds=2,
        hyperparameters={'n_estimators': 5}))
    service = FeatureImportanceService(TrainedModelCatalog(root), PredictorFactory(), datasets, root)
    return model, service, root, tmp_path


def test_training_persists_report_and_json_csv_api(trained, monkeypatch):
    model, service, root, tmp = trained
    report = service.get(model.id)
    assert report['data_source'] == 'external_test'
    assert report['sample_count'] == 12
    assert report['rankings'][0]['feature'] == 'signal'
    # A saved report can be read without its source data or loading the model.
    for path in (tmp / 'datasets').glob('*.csv'):
        path.unlink()
    monkeypatch.setenv('EDGEML_API_TOKEN', 'test-importance-api-token')
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_feature_importance_service] = lambda: service
    client = TestClient(app)
    url = f'/api/trained-models/{model.id}/feature-importance'
    assert client.get(url).status_code == 401
    headers = {'Authorization': 'Bearer test-importance-api-token'}
    response = client.get(url, headers=headers)
    assert response.status_code == 200 and response.json() == report
    response = client.get(url + '?format=csv', headers=headers)
    assert response.status_code == 200 and 'attachment' in response.headers['content-disposition']
    rows = list(csv.DictReader(io.StringIO(response.text.lstrip('\ufeff'))))
    assert rows[0]['feature'] == report['rankings'][0]['feature']
    assert float(rows[0]['importance']) == report['rankings'][0]['importance']
    assert client.get(url + '?format=xml', headers=headers).status_code == 422


def test_legacy_backfill_and_model_path_boundary(trained):
    model, service, root, _ = trained
    (root / model.id / 'feature_importance.json').unlink()
    app = create_app()
    app.dependency_overrides[get_feature_importance_service] = lambda: service
    client = TestClient(app)
    url = f'/api/trained-models/{model.id}/feature-importance'
    assert client.get(url).status_code == 409
    assert client.post(url).status_code == 200
    assert client.get(url).json()['rankings'][0]['feature'] == 'signal'
    assert client.get('/api/trained-models/missing/feature-importance').status_code == 404
    with pytest.raises(ModelNotFoundError):
        service.get('../outside')


def test_csv_quotes_headers_and_neutralizes_formulas():
    report = {'rankings': [{'rank': 1, 'feature': '=danger,"中文"', 'importance': -0.2, 'std': 0.1}]}
    row = next(csv.DictReader(io.StringIO(FeatureImportanceService.csv(report).lstrip('\ufeff'))))
    assert row['feature'] == '\'=danger,"中文"'
    assert row['importance'] == '-0.2'
