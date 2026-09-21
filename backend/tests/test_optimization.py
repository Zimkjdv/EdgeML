from datetime import date
import json
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.domain.schemas import ModelManifest
from app.domain.optimization import OptimizationRequest
from app.domain.errors import PredictionValidationError, ModelNotFoundError
from app.services.optimization_service import OptimizationService
from app.infrastructure.trained_model_catalog import TrainedModelCatalog
from app.api.dependencies import get_optimization_service, require_api_token
from app.main import create_app


class Catalog:
    def get(self, model_id):
        return ModelManifest(id=model_id, name='Test', version='1', framework='test', problem_type='regression', target='Y',
            features=[{'name':'x', 'dtype':'int64'}, {'name':'fixed', 'dtype':'float64'}, {'name':'kind', 'dtype':'object'}],
            author='test', created_at=date.today(), description='', model_path='.')


class Predictor:
    def predict(self, frame):
        assert (frame['fixed'] == 2).all()
        assert set(frame['kind']) <= {'A', 'B'}
        assert (frame['x'] % 2 == 0).all()
        return frame['x'].to_numpy() + frame['fixed'].to_numpy() + (frame['kind'] == 'B').to_numpy()*10


class Factory:
    def create(self, manifest): return Predictor()


def request(**changes):
    return OptimizationRequest.model_validate(dict(model_id='test', target=16, count=5,
        parameters=[{'name':'x','optimize':True,'minimum':0,'maximum':10,'step':2},
                    {'name':'fixed','value':2}, {'name':'kind','optimize':True,'choices':['A','B']}], **changes))


def test_search_respects_bounds_fixed_categories_and_reproducibility():
    service = OptimizationService(Catalog(), Factory())
    result = service.run(request())
    assert result == service.run(request())
    assert len(result.recommendations) == 5
    assert result.recommendations[0].prediction == 16
    assert result.recommendations[0].within_tolerance
    assert len({tuple(r.parameters.values()) for r in result.recommendations}) == 5
    assert result.evaluated <= 256*12
    assert result.best_error_by_iteration == sorted(result.best_error_by_iteration, reverse=True)
    assert all(0 <= r.parameters['x'] <= 10 for r in result.recommendations)


def test_unreachable_target_and_small_search_space():
    req = request()
    req.target = 1000
    req.parameters[0].maximum = 2
    req.parameters[2].choices = ['A']
    result = OptimizationService(Catalog(), Factory()).run(req)
    assert len(result.recommendations) == 2
    assert not any(r.within_tolerance for r in result.recommendations)


@pytest.mark.parametrize('change', ['missing','duplicate','fixed','bounds','step','choices','integer','classification'])
def test_invalid_feature_constraints(change):
    req = request()
    catalog = Catalog()
    if change == 'missing': req.parameters.pop()
    if change == 'duplicate': req.parameters.append(req.parameters[0])
    if change == 'fixed': req.parameters[1].value = None
    if change == 'bounds': req.parameters[0].maximum = -1
    if change == 'step': req.parameters[0].step = 20
    if change == 'choices': req.parameters[2].choices = []
    if change == 'integer': req.parameters[0].minimum = .1
    if change == 'classification':
        manifest = catalog.get('test'); manifest.problem_type = 'classification'
        catalog.get = lambda _: manifest
    with pytest.raises(PredictionValidationError):
        OptimizationService(catalog, Factory()).run(req)


def test_nonfinite_target_and_count_rejected():
    for value in [float('nan'), float('inf')]:
        payload = request().model_dump(); payload['target'] = value
        with pytest.raises(ValidationError): OptimizationRequest.model_validate(payload)
    payload = request().model_dump(); payload['count'] = 6
    with pytest.raises(ValidationError): OptimizationRequest.model_validate(payload)


@pytest.mark.parametrize('low,high,step', [(0.1, 0.3, 0.1), (-0.3, 0.3, 0.1), (1.1, 1.7, 0.2)])
def test_decimal_step_includes_aligned_endpoint(low, high, step):
    assert OptimizationService.snap_step(high, low, high, step) == high
    assert low <= OptimizationService.snap_step(high + 10, low, high, step) <= high


def test_step_does_not_include_unaligned_endpoint():
    assert OptimizationService.snap_step(0.35, 0.1, 0.35, 0.1) == 0.3


def test_achievable_candidates_precede_diverse_misses():
    catalog = Catalog()
    manifest = catalog.get('test')
    manifest.features = [manifest.features[0]]
    manifest.features[0].dtype = 'float64'
    catalog.get = lambda _: manifest
    class Identity:
        def predict(self, frame): return frame['x'].to_numpy()
    class IdentityFactory:
        def create(self, manifest): return Identity()
    req = OptimizationRequest(model_id='test', target=0, tolerance=.021, count=3,
        parameters=[{'name':'x','optimize':True,'minimum':0,'maximum':1,'step':.01, 'value':.5}], compare_baseline=True)
    result = OptimizationService(catalog, IdentityFactory()).run(req)
    assert len(result.recommendations) == 3
    assert all(r.within_tolerance for r in result.recommendations)
    assert result.baseline.prediction == .5
    assert result.baseline.parameters == {'x': .5}
    assert result.baseline.absolute_error == .5
    req.compare_baseline = False
    without = OptimizationService(catalog, IdentityFactory()).run(req)
    assert without.baseline is None
    assert without.evaluated == result.evaluated
    assert without.recommendations == result.recommendations
    req.parameters[0].minimum = .1
    req.parameters[0].maximum = .3
    req.parameters[0].step = .2
    endpoints = OptimizationService(catalog, IdentityFactory()).run(req)
    assert {r.parameters['x'] for r in endpoints.recommendations} == {.1, .3}


def test_missing_baseline_value_is_rejected():
    req = request()
    req.compare_baseline = True
    with pytest.raises(PredictionValidationError, match='baseline'):
        OptimizationService(Catalog(), Factory()).run(req)


def test_trained_catalog_and_path_boundary(tmp_path):
    folder = tmp_path/'model'; folder.mkdir()
    manifest = Catalog().get('model')
    (folder/'record.json').write_text(json.dumps({'manifest':manifest.model_dump(mode='json')}))
    catalog = TrainedModelCatalog(tmp_path)
    assert catalog.get('model').model_path == folder
    assert catalog.list()[0].id == 'model'
    with pytest.raises(ModelNotFoundError): catalog.get('../model')


def test_http_simulation_and_validation():
    app = create_app()
    app.dependency_overrides[require_api_token] = lambda: None
    app.dependency_overrides[get_optimization_service] = lambda: OptimizationService(Catalog(), Factory())
    with TestClient(app) as client:
        response = client.post('/api/optimization/simulate', json=request().model_dump())
        assert response.status_code == 200
        assert len(response.json()['recommendations']) == 5
        payload = request().model_dump(); payload['parameters'] = []
        assert client.post('/api/optimization/simulate', json=payload).status_code == 422


def test_real_sklearn_artifact(tmp_path):
    import joblib
    from sklearn.linear_model import LinearRegression
    import pandas as pd
    from app.infrastructure.predictor_factory import PredictorFactory
    folder = tmp_path / 'linear'; folder.mkdir()
    model = LinearRegression().fit(pd.DataFrame({'x':[0,1,2,3]}), [1,3,5,7])
    joblib.dump(model, folder / 'model.pkl')
    manifest = Catalog().get('linear')
    manifest.features = [manifest.features[0]]
    manifest.framework = 'sklearn'
    (folder/'record.json').write_text(json.dumps({'manifest':manifest.model_dump(mode='json')}))
    req = OptimizationRequest(model_id='linear', target=5, parameters=[{'name':'x','optimize':True,'minimum':0,'maximum':4,'step':1}])
    result = OptimizationService(TrainedModelCatalog(tmp_path), PredictorFactory()).run(req)
    assert result.recommendations[0].parameters['x'] == 2
    assert result.recommendations[0].prediction == pytest.approx(5)


def test_defaults_use_linked_training_data_and_survive_dataset_deletion(tmp_path):
    from app.services.dataset_service import DatasetService
    from app.services.optimization_defaults import OptimizationDefaults
    from app.domain.feature_defaults import summarize_features
    datasets = DatasetService(tmp_path/'datasets')
    data = datasets.upload('train.csv', b'x,fixed,kind,Y\n0,2,A,1\n2,4,B,2\n4,6,A,3\n999,999,Z,\n')
    root = tmp_path/'trained'; folder = root/'test'; folder.mkdir(parents=True)
    (folder/'record.json').write_text(json.dumps({'settings':{'dataset_id':data.id}}))
    provider = OptimizationDefaults(root, datasets)
    manifest = Catalog().get('test')
    defaults = provider.get(manifest)
    assert defaults['origin'] == 'source_dataset'
    assert defaults['features']['x']['maximum'] == 4
    assert defaults['features']['x']['value'] == 2
    assert defaults['features']['kind']['value'] == 'A'
    assert defaults['features']['kind']['choices'] == ['A','B']
    manifest.feature_defaults = defaults['features']
    manifest.training_dataset_id = data.id
    datasets.delete(data.id)
    assert provider.get(manifest)['origin'] == 'training_snapshot'
    manifest.feature_defaults = {}
    assert provider.get(manifest)['origin'] == 'unavailable'
