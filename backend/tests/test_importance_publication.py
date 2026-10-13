import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_feature_importance_service, get_training_service
from app.domain.errors import PredictionValidationError
from app.infrastructure.file_model_registry import FileModelRegistry
from app.main import create_app
from app.services.feature_importance_service import FeatureImportanceService, PublishedFeatureImportanceService
from app.services.training_service import TrainingService
from test_feature_importance import trained


def configured(trained):
    model, source, root, tmp = trained
    registry = FileModelRegistry(tmp / 'registry.json', tmp / 'published')
    training = TrainingService(source.datasets, root, tmp / 'published', model_registry=registry)
    importance = FeatureImportanceService(source.catalog, source.factory, source.datasets, root, tmp / 'published', registry)
    return model, training, importance, registry, tmp / 'published'


def test_recompute_refresh_preserves_disabled_artifact_metrics_and_canonical_id(trained):
    model, training, importance, registry, published = configured(trained)
    assert importance.get(model.id)['publication']['status'] == 'draft'
    training.publish(model.id)
    assert importance.get(model.id)['publication']['status'] == 'current'
    package = published / model.id
    artifact = (package / 'model.pkl').read_bytes()
    record = (importance.root / model.id / 'record.json').read_bytes()
    registry.set_status(model.id, 'disabled')
    # The same canonical ID may live in a legacy human-readable folder.
    legacy = published / '中文套件'
    package.rename(legacy)
    manifest = training.get(model.id).manifest
    from app.domain.schemas import ModelManifest
    registry.register(ModelManifest.model_validate({**manifest, 'model_path': legacy}), legacy.name)
    registry.set_status(model.id, 'disabled')
    importance.compute(model.id)
    assert importance.get(model.id)['publication']['status'] == 'stale'
    training.refresh_importance_snapshot(model.id)
    state = importance.get(model.id)['publication']
    assert state['status'] == 'current' and state['registry_status'] == 'disabled'
    assert state['published_at'] and state['published_computed_at']
    assert (legacy / 'model.pkl').read_bytes() == artifact
    assert (importance.root / model.id / 'record.json').read_bytes() == record
    registry.set_status(model.id, 'active')
    assert PublishedFeatureImportanceService(registry).get(model.id)['computed_at'] == importance.get(model.id)['computed_at']


def test_snapshot_conflicts_and_failed_replace_keep_old_snapshot(trained, monkeypatch):
    model, training, importance, registry, published = configured(trained)
    with pytest.raises(PredictionValidationError):
        training.refresh_importance_snapshot(model.id)
    training.publish(model.id)
    package = published / model.id
    saved = (package / 'feature_importance.json').read_bytes()
    artifact = (package / 'model.pkl').read_bytes()
    (package / 'model.pkl').write_bytes(b'changed')
    with pytest.raises(PredictionValidationError, match='differ'):
        training.refresh_importance_snapshot(model.id)
    assert (package / 'feature_importance.json').read_bytes() == saved
    (package / 'model.pkl').write_bytes(artifact)
    import app.services.feature_importance_service as module
    monkeypatch.setattr(module.os, 'replace', lambda *_: (_ for _ in ()).throw(OSError('disk error')))
    with pytest.raises(OSError):
        training.refresh_importance_snapshot(model.id)
    assert (package / 'feature_importance.json').read_bytes() == saved
    assert not list(package.glob('importance-*.tmp'))


def test_refresh_api_auth_and_missing_snapshot_backfill(trained, monkeypatch):
    model, training, importance, registry, published = configured(trained)
    training.publish(model.id)
    (published / model.id / 'feature_importance.json').unlink()
    assert importance.get(model.id)['publication']['status'] == 'missing'
    from app.core.config import get_settings
    monkeypatch.setenv('EDGEML_API_TOKEN', 'synthetic-importance-token')
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_training_service] = lambda: training
    app.dependency_overrides[get_feature_importance_service] = lambda: importance
    client = TestClient(app)
    url = f'/api/trained-models/{model.id}/feature-importance/publish'
    assert client.post(url).status_code == 401
    response = client.post(url, headers={'Authorization': 'Bearer synthetic-importance-token'})
    assert response.status_code == 200 and response.json()['publication']['status'] == 'current'
    registry.unregister(model.id)
    assert importance.get(model.id)['publication']['status'] == 'unregistered'
    assert client.post(url, headers={'Authorization': 'Bearer synthetic-importance-token'}).status_code == 409


def test_compute_serializes_with_model_mutation(trained, monkeypatch):
    model, training, importance, _, _ = configured(trained)
    entered, release = Event(), Event()
    original = importance._compute
    def blocked(model_id):
        entered.set()
        assert release.wait(5)
        return original(model_id)
    monkeypatch.setattr(importance, '_compute', blocked)
    with ThreadPoolExecutor(2) as pool:
        computation = pool.submit(importance.compute, model.id)
        assert entered.wait(5)
        rename = pool.submit(training.rename, model.id, '新名稱')
        assert not rename.done()
        release.set()
        computation.result()
        assert rename.result().name == '新名稱'
