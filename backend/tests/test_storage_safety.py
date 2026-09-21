import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.domain.schemas import ModelManifest
from app.infrastructure.file_model_registry import FileModelRegistry
from app.infrastructure.model_storage import initialize_model_storage
from app.services.training_service import TrainingService
from scripts.migrate_model_storage import migrate


def manifest(root, model_id='model-1', name='紙種模型'):
    return ModelManifest(id=model_id, name=name, version='1.0', framework='sklearn',
        problem_type='regression', target='y', features=[], author='test',
        created_at='2026-09-21', description='test', model_path=root / model_id)


def trained_service(root, name='紙種模型'):
    registry = FileModelRegistry(root / 'registry.json', root / 'published')
    service = TrainingService(None, root / 'trained', root / 'published', model_registry=registry)
    model = manifest(root / 'trained', name=name)
    folder = model.model_path
    folder.mkdir()
    record = dict(id=model.id, name=name, completed_at=datetime.now(timezone.utc).isoformat(),
        target_column='y', algorithm='random_forest', status='draft', feature_columns=[],
        validation_metrics={}, settings={}, manifest=model.model_dump(mode='json'))
    (folder / 'record.json').write_text(json.dumps(record), encoding='utf-8')
    (folder / 'metadata.json').write_text(model.model_dump_json(), encoding='utf-8')
    (folder / 'model.pkl').write_bytes(b'trusted test artifact; not deserialized')
    return service, registry


def test_publish_uses_id_even_for_path_like_display_name(tmp_path):
    service, registry = trained_service(tmp_path, '../outside')
    outside = tmp_path / 'outside-model-1'
    outside.mkdir()
    (outside / 'sentinel').write_text('keep')
    service.publish('model-1')
    assert registry.get('model-1').model_path == tmp_path / 'published' / 'model-1'
    assert (outside / 'sentinel').read_text() == 'keep'
    service.rename('model-1', '新名稱')
    service.publish('model-1')
    assert registry.get('model-1').name == '新名稱'
    assert len(list((tmp_path / 'published').glob('*/model.pkl'))) == 1


@pytest.mark.parametrize('identifier', ['../outside', '..\\outside', '/tmp/outside', 'C:\\outside', '..'])
def test_model_operations_reject_paths(tmp_path, identifier):
    service, _ = trained_service(tmp_path)
    for operation in (service.get, service.publish, lambda v: service.rename(v, 'new'), lambda v: service.delete_many([v])):
        with pytest.raises(ModelNotFoundError):
            operation(identifier)


def test_failed_copy_does_not_register_partial_package(tmp_path, monkeypatch):
    service, registry = trained_service(tmp_path)
    def fail(*args, **kwargs):
        raise OSError('disk unavailable')
    monkeypatch.setattr('app.services.training_service.shutil.copytree', fail)
    with pytest.raises(OSError):
        service.publish('model-1')
    assert not (tmp_path / 'published' / 'model-1').exists()
    assert registry.list() == []
    assert list((tmp_path / 'published').glob('.publish-*')) == []


def test_missing_existing_artifact_is_not_silently_republished(tmp_path):
    service, _ = trained_service(tmp_path)
    service.publish('model-1')
    (tmp_path / 'published' / 'model-1' / 'model.pkl').unlink()
    with pytest.raises(PredictionValidationError, match='missing'):
        service.publish('model-1')


def test_storage_seed_and_legacy_migration_survive_new_instances(tmp_path):
    old = tmp_path / 'old-container'
    (old / 'legacy-name-12345678').mkdir(parents=True)
    (old / 'legacy-name-12345678' / 'model.pkl').write_bytes(b'original')
    (old / 'legacy-name-12345678' / 'metadata.json').write_text('{}')
    persistent = tmp_path / 'volume' / 'published_models'
    assert migrate(old, persistent) == 1
    assert migrate(old, persistent) == 0
    (old / 'legacy-name-12345678' / 'model.pkl').write_bytes(b'new image seed')
    settings = SimpleNamespace(models_root=persistent, bundled_models_root=old)
    initialize_model_storage(settings)
    initialize_model_storage(settings)
    assert (persistent / 'legacy-name-12345678' / 'model.pkl').read_bytes() == b'original'
    with pytest.raises(RuntimeError, match='conflict'):
        migrate(old, persistent)
    assert (persistent / 'legacy-name-12345678' / 'model.pkl').read_bytes() == b'original'


def _register_many(root, prefix):
    root = Path(root)
    for i in range(6):
        registry = FileModelRegistry(root / 'registry.json', root / 'models')
        registry.register(manifest(root / 'models', f'{prefix}-{i}'))
        registry.set_status(f'{prefix}-{i}', 'disabled')


def test_registry_cross_process_transactions(tmp_path):
    (tmp_path / 'models').mkdir()
    with ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context('spawn')) as executor:
        futures = [executor.submit(_register_many, str(tmp_path), prefix) for prefix in ('a', 'b')]
        for future in futures:
            future.result(timeout=60)
    items = FileModelRegistry(tmp_path / 'registry.json', tmp_path / 'models').list_registry()
    assert len(items) == 12
    assert all(item.status == 'disabled' for item in items)
    assert not list(tmp_path.glob('registry-*.tmp'))


def test_invalid_registry_is_preserved(tmp_path):
    registry_file = tmp_path / 'registry.json'
    registry_file.write_text('{}')
    registry = FileModelRegistry(registry_file, tmp_path / 'models')
    with pytest.raises(ValueError):
        registry.register(manifest(tmp_path / 'models'))
    assert registry_file.read_text() == '{}'
