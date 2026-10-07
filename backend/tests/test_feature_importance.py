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
from app.domain.schemas import ModelManifest
from app.domain.training_schemas import TrainingRequest
from app.infrastructure.file_model_registry import FileModelRegistry
from app.infrastructure.predictor_factory import PredictorFactory
from app.infrastructure.trained_model_catalog import TrainedModelCatalog
from app.main import create_app
from app.services.dataset_service import DatasetService
from app.services.feature_importance_service import FeatureImportanceService, PublishedFeatureImportanceService, calculate_importance, save_importance
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


@pytest.fixture
def published(tmp_path, monkeypatch):
    root = tmp_path / 'published'
    package = root / '中文套件目錄'
    package.mkdir(parents=True)
    manifest = ModelManifest(id='prediction-model-id', name='中文模型', version='1.0.0',
        framework='sklearn', problem_type='regression', target='強度',
        features=[{'name': '基重', 'dtype': 'float64'}], author='tests',
        created_at='2026-10-07', description='API fixture', model_path=package)
    registry_file = tmp_path / 'registry.json'
    registry = FileModelRegistry(registry_file, root)
    registry.register(manifest)
    report = {'method': 'permutation', 'metric': 'rmse_increase', 'baseline_score': 0.123456789,
        'dataset_id': 'removed-dataset', 'data_source': 'training', 'sample_count': 30,
        'total_rows': 80, 'repeats': 3, 'seed': 42, 'computed_at': '2026-10-07T00:00:00Z',
        'rankings': [{'rank': i + 1, 'feature': f'中文特徵{i}',
                      'importance': 0.123456789 - i * 0.01, 'std': 0.0123456789}
                     for i in range(20)]}
    save_importance(package, report)
    monkeypatch.setenv('EDGEML_MODELS_ROOT', str(root))
    monkeypatch.setenv('EDGEML_MODEL_REGISTRY_FILE', str(registry_file))
    get_settings.cache_clear()
    return manifest, registry, package, report


def test_prediction_id_api_reads_complete_snapshot_without_training_or_inference(published, monkeypatch):
    manifest, _, _, saved = published
    monkeypatch.setenv('EDGEML_API_TOKEN', 'published-importance-test-token')
    get_settings.cache_clear()

    def forbidden(*args, **kwargs):
        pytest.fail('Report GET must not read source data or load a model.')

    monkeypatch.setattr(DatasetService, 'frame', forbidden)
    monkeypatch.setattr(PredictorFactory, 'create', forbidden)
    client = TestClient(create_app())
    url = f'/api/models/{manifest.id}/feature-importance'
    assert client.get(url).status_code == 401
    headers = {'Authorization': 'Bearer published-importance-test-token'}
    response = client.get(url, headers=headers)
    assert response.status_code == 200
    report = response.json()
    assert report == {**saved, 'model_id': manifest.id, 'model_name': manifest.name}
    assert len(report['rankings']) == 20 and report['rankings'][-1]['importance'] < 0
    response = client.get(url + '?format=csv', headers=headers)
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/csv')
    assert 'attachment' in response.headers['content-disposition']
    rows = list(csv.DictReader(io.StringIO(response.text.lstrip('\ufeff'))))
    assert len(rows) == 20
    for actual, expected in zip(rows, report['rankings']):
        assert actual['feature'] == expected['feature']
        assert actual['model_id'] == manifest.id
        assert float(actual['importance']) == expected['importance']
        assert float(actual['std']) == expected['std']
    assert client.get(url + '?format=xml', headers=headers).status_code == 422
    assert client.post(url, headers=headers).status_code == 405


def test_published_lookup_uses_active_model_id_not_package_directory(published):
    manifest, registry, package, _ = published
    client = TestClient(create_app())
    assert client.get('/api/models/missing/feature-importance').status_code == 404
    assert client.get(f'/api/models/{package.name}/feature-importance').status_code == 404
    registry.set_status(manifest.id, 'disabled')
    assert client.get(f'/api/models/{manifest.id}/feature-importance').status_code == 404


@pytest.mark.parametrize('invalid', [None, '{broken json', '[]', '{"rankings": []}',
                                     '{"baseline_score": NaN}'])
def test_published_missing_or_invalid_snapshot_returns_conflict(published, invalid):
    manifest, _, package, _ = published
    path = package / 'feature_importance.json'
    if invalid is None:
        path.unlink()
    else:
        path.write_text(invalid, encoding='utf-8')
    client = TestClient(create_app())
    assert client.get(f'/api/models/{manifest.id}/feature-importance').status_code == 409


def test_published_nonfinite_ranking_is_rejected(published):
    manifest, _, package, saved = published
    saved['rankings'][0]['importance'] = float('inf')
    (package / 'feature_importance.json').write_text(json.dumps(saved), encoding='utf-8')
    client = TestClient(create_app())
    assert client.get(f'/api/models/{manifest.id}/feature-importance').status_code == 409


def test_explicit_republish_refreshes_importance_without_replacing_artifact(trained):
    model, service, root, tmp = trained
    training = TrainingService(service.datasets, root, tmp / 'published')
    training.publish(model.id)
    destination = tmp / 'published' / model.id
    catalog = FileModelRegistry(tmp / 'registry.json', tmp / 'published')
    catalog.register(ModelManifest.model_validate({**model.manifest, 'model_path': destination}))
    published_service = PublishedFeatureImportanceService(catalog)
    artifact = (destination / 'model.pkl').read_bytes()
    previous = published_service.get(model.id)
    updated = service.get(model.id)
    updated['rankings'][0]['importance'] += 0.5
    save_importance(root / model.id, updated)
    assert published_service.get(model.id) == previous
    # Older published packages can receive a backfilled report on explicit publish.
    (destination / 'feature_importance.json').unlink()
    training.publish(model.id)
    assert published_service.get(model.id) == updated
    assert (destination / 'model.pkl').read_bytes() == artifact
