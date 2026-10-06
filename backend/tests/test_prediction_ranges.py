from datetime import date
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_prediction_service
from app.domain.errors import PredictionValidationError
from app.domain.schemas import FeatureSpec, ModelManifest
from app.main import create_app
from app.services.prediction_service import PredictionService


@pytest.fixture
def ranged_service(tmp_path):
    manifest = ModelManifest(id='ranges', name='範圍模型', version='1.0.0', framework='sklearn',
        problem_type='regression', target='實際值', author='Test', created_at=date(2026, 10, 6),
        description='Isolated synthetic model', model_path=tmp_path,
        features=[FeatureSpec(name='車速', dtype='float64'), FeatureSpec(name='紙種', dtype='object')],
        feature_defaults={'車速': {'minimum': 410, 'maximum': 950}})
    predictor = Mock()
    predictor.predict.side_effect = lambda frame: np.full(len(frame), 7.123456)
    factory, history = Mock(), Mock()
    factory.create.return_value = predictor
    service = PredictionService(SimpleNamespace(get=lambda _: manifest), factory, history)
    return service, manifest, factory, history


def send(service, transport, records, policy='drop', **extra):
    app = create_app()
    app.dependency_overrides[get_prediction_service] = lambda: service
    with TestClient(app) as client:
        fields = {'model_id': 'ranges', **extra}
        if policy is not None:
            fields['training_range_policy'] = policy
        if transport == 'json':
            return client.post('/api/predict/json', json={**fields, 'data': records})
        content = pd.DataFrame(records).to_csv(index=False).encode('utf-8')
        return client.post('/api/predict', data=fields,
            files={'file': ('中文.csv', content, 'text/csv')})


@pytest.mark.parametrize('transport', ['csv', 'json'])
def test_range_drop_preserves_identity_counts_and_inclusive_bounds(ranged_service, transport):
    service, _, factory, history = ranged_service
    records = [{'row_id': i, '車速': value, '紙種': '甲', '其他欄位': None}
               for i, value in enumerate([410, 409.9, None, 950, 950.1])]
    response = send(service, transport, records)
    assert response.status_code == 200
    if transport == 'json':
        output = response.json()
        assert output['dropped_rows'] == 3
        assert output['out_of_range_rows'] == 2
        assert [r['row_id'] for r in output['records']] == [0, 3]
    else:
        assert response.headers['X-Prediction-Dropped-Rows'] == '3'
        assert response.headers['X-Prediction-Out-Of-Range-Rows'] == '2'
        assert pd.read_csv(StringIO(response.text)).row_id.tolist() == [0, 3]
    assert factory.create.return_value.predict.call_args.args[0]['車速'].tolist() == [410, 950]
    assert history.add.call_args.args[0].row_count == 2


@pytest.mark.parametrize('transport', ['csv', 'json'])
def test_default_still_allows_extrapolation_without_snapshot(ranged_service, transport):
    service, manifest, _, _ = ranged_service
    manifest.feature_defaults = {}
    response = send(service, transport, [{'車速': 1000, '紙種': '甲'}], policy=None)
    assert response.status_code == 200
    if transport == 'json':
        assert response.json()['out_of_range_rows'] == 0
        assert len(response.json()['records']) == 1


@pytest.mark.parametrize('bounds', [{}, {'minimum': None, 'maximum': 950},
    {'minimum': 950, 'maximum': 410}, {'minimum': 'NaN', 'maximum': 950},
    {'minimum': 410, 'maximum': 'Infinity'}, {'minimum': True, 'maximum': 950}])
@pytest.mark.parametrize('transport', ['csv', 'json'])
def test_missing_or_bad_snapshot_fails_before_inference_and_history(ranged_service, transport, bounds):
    service, manifest, factory, history = ranged_service
    manifest.feature_defaults = {'車速': bounds}
    response = send(service, transport, [{'車速': 730, '紙種': '甲'}])
    assert response.status_code == 422
    assert '訓練範圍快照' in response.json()['detail']
    factory.create.assert_not_called()
    history.add.assert_not_called()


@pytest.mark.parametrize('transport', ['csv', 'json'])
def test_all_rows_outside_range_returns_422_without_predictions(ranged_service, transport):
    service, _, factory, history = ranged_service
    response = send(service, transport, [{'車速': 1000, '紙種': '甲'}])
    assert response.status_code == 422
    assert '沒有可預測' in response.json()['detail']
    factory.create.assert_not_called()
    history.add.assert_not_called()


@pytest.mark.parametrize('transport', ['csv', 'json'])
def test_invalid_numeric_is_not_silently_dropped_by_range_policy(ranged_service, transport):
    service, _, factory, _ = ranged_service
    response = send(service, transport, [{'車速': 730, '紙種': '甲'}, {'車速': 'bad', '紙種': '甲'}])
    assert response.status_code == 422
    factory.create.assert_not_called()


@pytest.mark.parametrize('transport', ['csv', 'json'])
def test_unknown_policy_returns_422(ranged_service, transport):
    service, _, factory, _ = ranged_service
    response = send(service, transport, [{'車速': 730, '紙種': '甲'}], policy='unexpected')
    assert response.status_code == 422
    factory.create.assert_not_called()


@pytest.mark.parametrize('dtype', ['int64', 'uint64'])
@pytest.mark.parametrize('transport', ['csv', 'json'])
def test_exact_large_integer_range_is_not_rounded(ranged_service, dtype, transport):
    service, manifest, factory, _ = ranged_service
    high = 9223372036854775807 if dtype == 'int64' else 18446744073709551615
    manifest.features = [FeatureSpec(name='x', dtype=dtype)]
    manifest.feature_defaults = {'x': {'minimum': str(high), 'maximum': str(high)}}
    if transport == 'csv':
        output = service.predict_csv('ranges', f'x\n{high}\n{high - 1}\n'.encode(), training_range_policy='drop')
        assert str(high) in output.csv_content.decode()
    else:
        output = service.predict_json('ranges', [{'x': str(high)}, {'x': str(high - 1)}], training_range_policy='drop')
        assert output.records[0]['x'] == high
    assert output.dropped_rows == output.out_of_range_rows == 1
    assert factory.create.return_value.predict.call_args.args[0].x.tolist() == [high]


def test_optional_missing_numeric_and_categories_are_not_excluded(ranged_service):
    service, manifest, _, _ = ranged_service
    manifest.features.append(FeatureSpec(name='optional', dtype='float64', required=False))
    manifest.feature_defaults['optional'] = {'minimum': 0, 'maximum': 1}
    output = service.predict_json('ranges', [{'車速': 730, '紙種': '未見過的類別'},
        {'車速': 730, '紙種': '甲', 'optional': None}], training_range_policy='drop')
    assert len(output.records) == 2
    assert output.out_of_range_rows == 0


def test_ground_truth_metrics_only_use_remaining_rows(ranged_service):
    service, _, _, _ = ranged_service
    result = service.predict_json('ranges', [{'車速': 730, '紙種': '甲', '實際值': 7},
        {'車速': 731, '紙種': '甲', '實際值': None}, {'車速': 1000, '紙種': '甲', '實際值': -1000}],
        training_range_policy='drop')
    assert len(result.records) == 1
    assert result.dropped_rows == 2
    assert result.out_of_range_rows == 1
    assert result.metrics['mae'] == pytest.approx(0.123456)


def test_service_rejects_unknown_policy(ranged_service):
    service, _, _, _ = ranged_service
    with pytest.raises(PredictionValidationError, match='training_range_policy'):
        service.predict_json('ranges', [{'車速': 730, '紙種': '甲'}], training_range_policy='unexpected')


def test_float32_regression_predictions_do_not_expand_in_json(ranged_service):
    service, _, factory, _ = ranged_service
    factory.create.return_value.predict.side_effect = lambda frame: np.full(len(frame), 9.261934, dtype=np.float32)
    output = service.predict_json('ranges', [{'車速': 730, '紙種': '甲'}], training_range_policy='drop')
    assert output.records[0]['prediction'] == 9.2619
    assert len(str(output.records[0]['prediction']).split('.')[1]) <= 4
