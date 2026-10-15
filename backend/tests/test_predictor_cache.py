from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from datetime import date
import json
import time

import numpy as np
import pandas as pd
import pytest

from app.domain.errors import ModelNotFoundError, WorkloadBusyError
from app.domain.schemas import ModelManifest
from app.infrastructure.cached_predictor_provider import CachedPredictorProvider
from app.infrastructure.file_model_registry import FileModelRegistry
from app.predictors.base import BasePredictor
from app.services.model_registry_service import ModelRegistryService
from app.services.prediction_service import PredictionService


def manifest(root, name='one', preprocessor=False):
    folder = root / name; folder.mkdir(exist_ok=True)
    (folder / 'model.pkl').write_bytes(b'1')
    if preprocessor: (folder / 'preprocess.pkl').write_bytes(b'1')
    model = ModelManifest(id=name, name=name, version='1.0.0', framework='sklearn', problem_type='regression',
        target='target', features=[{'name':'x','dtype':'int64'}], prediction_column='prediction', author='test',
        created_at=date(2026,10,15), description='synthetic', model_path=folder,
        preprocess_artifact='preprocess.pkl' if preprocessor else None)
    (folder / 'metadata.json').write_text(model.model_dump_json(), encoding='utf-8')
    return model


class Factory:
    def __init__(self):
        self.count, self.guard, self.entered, self.release, self.fail = 0, Lock(), Event(), Event(), False
        self.active, self.peak = 0, 0
        self.release.set()
    def create(self, model):
        owner = self
        class Predictor(BasePredictor):
            def load(self):
                with owner.guard: owner.count += 1
                owner.entered.set()
                assert owner.release.wait(5)
                if owner.fail: raise ValueError('synthetic load failure')
                self.value = int((model.model_path / model.artifact).read_text())
            def predict(self, df):
                with owner.guard:
                    owner.active += 1; owner.peak = max(owner.peak, owner.active)
                try:
                    time.sleep(0.005)
                    return np.repeat(self.value, len(df))
                finally:
                    with owner.guard: owner.active -= 1
            def metadata(self): return model
        return Predictor()


def test_singleflight_loads_once_and_delegates_base_contract(tmp_path):
    model = manifest(tmp_path); factory = Factory(); factory.release.clear()
    cache = CachedPredictorProvider(factory)
    with ThreadPoolExecutor(8) as pool:
        tasks = [pool.submit(cache.create, model) for _ in range(8)]
        assert factory.entered.wait(5)
        factory.release.set()
        objects = [task.result() for task in tasks]
    assert all(item is objects[0] for item in objects) and factory.count == 1
    objects[0].load(); assert factory.count == 1
    assert objects[0].predict(pd.DataFrame({'x':[1]})).tolist() == [1]
    assert objects[0].predict_proba(pd.DataFrame({'x':[1]})) is None
    with pytest.raises(NotImplementedError): objects[0].explain(pd.DataFrame({'x':[1]}))
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: objects[0].predict(pd.DataFrame({'x':[1]})),range(8)))
    assert factory.peak == 1


def test_artifact_replacement_during_load_rejects_result(tmp_path):
    from app.domain.errors import PredictionValidationError
    model = manifest(tmp_path); factory = Factory(); factory.release.clear()
    cache = CachedPredictorProvider(factory)
    with ThreadPoolExecutor(1) as pool:
        task = pool.submit(cache.create,model); assert factory.entered.wait(5)
        stage = model.model_path / 'new.pkl'; stage.write_bytes(b'2'); stage.replace(model.model_path/'model.pkl')
        factory.release.set()
        with pytest.raises(PredictionValidationError): task.result()
    assert cache.info()['entries'] == 0
    assert cache.create(model).predict(pd.DataFrame({'x':[1]})).tolist() == [2]


def test_lru_byte_limit_oversized_and_disabled_cache(tmp_path):
    models = [manifest(tmp_path, name) for name in ('one','two','three')]
    factory = Factory(); cache = CachedPredictorProvider(factory, max_entries=2, max_artifact_bytes=2)
    one = cache.create(models[0]); cache.create(models[1]); assert cache.create(models[0]) is one
    cache.create(models[2]); cache.create(models[1])
    assert factory.count == 4 and cache.info() == {'entries':2,'artifact_bytes':2,'loading':0}
    tiny = CachedPredictorProvider(factory, max_artifact_bytes=0)
    assert tiny.create(models[0]) is not tiny.create(models[0]) and tiny.info()['entries'] == 0
    disabled = CachedPredictorProvider(factory, max_entries=0)
    assert disabled.create(models[0]) is not disabled.create(models[0])


def test_changed_metadata_artifact_preprocessor_and_deleted_files_never_reuse(tmp_path):
    model = manifest(tmp_path, preprocessor=True); cache = CachedPredictorProvider(Factory())
    first = cache.create(model)
    new = model.model_copy(update={'version':'2.0.0','name':'新名稱'})
    assert cache.create(new) is not first
    old = cache.create(new)
    stage = model.model_path / 'new.pkl'; stage.write_bytes(b'2'); stage.replace(model.model_path / 'model.pkl')
    current = cache.create(new)
    assert current is not old and current.predict(pd.DataFrame({'x':[1]})).tolist() == [2]
    stage.write_bytes(b'3'); stage.replace(model.model_path / 'preprocess.pkl')
    assert cache.create(new) is not current
    (model.model_path / 'model.pkl').unlink()
    with pytest.raises(ModelNotFoundError): cache.create(new)
    assert cache.info()['entries'] == 0


def test_failure_and_inflight_invalidation_do_not_publish_stale_runtime(tmp_path):
    model = manifest(tmp_path); factory = Factory(); cache = CachedPredictorProvider(factory)
    factory.fail = True
    with pytest.raises(ValueError): cache.create(model)
    assert cache.info() == {'entries':0,'artifact_bytes':0,'loading':0}
    factory.fail = False; factory.entered.clear(); factory.release.clear()
    with ThreadPoolExecutor(1) as pool:
        task = pool.submit(cache.create, model)
        assert factory.entered.wait(5)
        cache.invalidate(model.id); factory.release.set(); task.result()
    assert cache.info()['entries'] == 0
    cache.create(model); assert cache.info()['entries'] == 1


def test_different_model_load_capacity_is_bounded(tmp_path):
    first, second = manifest(tmp_path), manifest(tmp_path, 'two')
    factory = Factory(); factory.release.clear(); cache = CachedPredictorProvider(factory, max_loads=1)
    with ThreadPoolExecutor(1) as pool:
        task = pool.submit(cache.create, first); assert factory.entered.wait(5)
        with pytest.raises(WorkloadBusyError): cache.create(second)
        factory.release.set(); task.result()
    assert cache.create(second).metadata().id == 'two'


def test_registry_remains_authoritative_and_administration_evicts(tmp_path):
    root = tmp_path / 'models'; root.mkdir(); model = manifest(root)
    registry = FileModelRegistry(tmp_path / 'registry.json', root); registry.register(model)
    cache = CachedPredictorProvider(Factory())
    class History:
        def add(self, record): pass
    service = PredictionService(registry, cache, History(), cache.invalidate)
    admin = ModelRegistryService(registry, cache.invalidate)
    assert service.predict_json(model.id,[{'x':1}]).records[0]['prediction'] == 1
    admin.set_status(model.id, 'disabled'); assert cache.info()['entries'] == 0
    with pytest.raises(ModelNotFoundError): service.predict_json(model.id,[{'x':1}])
    admin.set_status(model.id, 'active'); service.predict_json(model.id,[{'x':1}])
    admin.unregister(model.id)
    with pytest.raises(ModelNotFoundError): service.predict_json(model.id,[{'x':1}])
    assert cache.info()['entries'] == 0
