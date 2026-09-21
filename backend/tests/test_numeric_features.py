from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from app.domain.errors import PredictionValidationError
from app.domain.schemas import FeatureSpec
from app.services.prediction_service import PredictionService
from test_api import client


@pytest.mark.parametrize('dtype,value', [
    ('int64', '1.9'), ('int64', '1/2'), ('int64', '1.00000000000000001'),
    ('int64', 'NaN'), ('int64', 'inf'), ('int64', '-inf'),
    ('int8', '128'), ('int8', '-129'), ('uint8', '-1'), ('uint8', '256'),
    ('int64', '9223372036854775808'), ('int64', '-9223372036854775809'),
    ('uint64', '18446744073709551616'), ('float64', 'inf'), ('float32', '1e39'),
])
@pytest.mark.parametrize('with_missing', [False, True])
def test_reject_invalid_numbers_even_when_another_row_is_missing(dtype, value, with_missing):
    frame = pd.DataFrame({'數值': [value, None] if with_missing else [value]}, dtype=object)
    with pytest.raises(PredictionValidationError, match='數值'):
        PredictionService._validate_frame(frame, [FeatureSpec(name='數值', dtype=dtype)])


@pytest.mark.parametrize('dtype,values', [
    ('int8', [-128, 127]), ('int64', [-9223372036854775808, 9223372036854775807]),
    ('uint64', [0, 18446744073709551615]), ('Int64', [1, 2]),
])
def test_integer_bounds_and_missing_values_are_exact(dtype, values):
    frame = pd.DataFrame({'x': [str(value) for value in values] + [None]}, dtype=object)
    PredictionService._validate_frame(frame, [FeatureSpec(name='x', dtype=dtype)])
    assert frame.x.iloc[:2].tolist() == values
    assert pd.isna(frame.x.iloc[2])


def test_integral_decimals_and_floats_are_supported():
    frame = pd.DataFrame({'x': ['2.0', '3e1'], 'y': ['1.9', None]}, dtype=object)
    PredictionService._validate_frame(frame, [FeatureSpec(name='x', dtype='int64'), FeatureSpec(name='y', dtype='float32')])
    assert frame.x.tolist() == [2, 30]
    assert frame.y.iloc[0] == pytest.approx(1.9)
    assert pd.isna(frame.y.iloc[1])


@pytest.mark.parametrize('transport', ['csv', 'json'])
def test_http_prediction_rejects_fractional_integer_feature(transport):
    browser = client()
    if transport == 'csv':
        response = browser.post('/api/predict', data={'model_id': 'house-price-v1'},
            files={'file': ('test.csv', b'Area,Room,Age\n80,1.9,15\n80,,15\n', 'text/csv')})
    else:
        response = browser.post('/api/predict/json', json={'model_id': 'house-price-v1',
            'data': [{'Area': 80, 'Room': 1.9, 'Age': 15}, {'Area': 80, 'Room': None, 'Age': 15}]})
    assert response.status_code == 422
    assert 'Room' in response.json()['detail']


@pytest.mark.parametrize('transport', ['csv', 'json'])
def test_prediction_preserves_int64_before_missing_row_cleanup(transport):
    seen = []
    manifest = SimpleNamespace(id='exact', name='Exact', target='y', problem_type='regression',
        prediction_column='prediction', features=[FeatureSpec(name='x', dtype='int64')])

    def predict(frame):
        seen.extend(frame.x.tolist())
        return np.zeros(len(frame))

    service = PredictionService(SimpleNamespace(get=lambda _: manifest),
        SimpleNamespace(create=lambda _: SimpleNamespace(predict=predict)), SimpleNamespace(add=lambda _: None))
    value = 9223372036854775807
    if transport == 'csv':
        result = service.predict_csv('exact', f'x,extra\n{value},a\n,b\n'.encode())
        assert str(value) in result.csv_content.decode()
    else:
        result = service.predict_json('exact', [{'x': value}, {'x': None}])
        assert result.records[0]['x'] == value
    assert seen == [value]
    assert result.dropped_rows == 1
