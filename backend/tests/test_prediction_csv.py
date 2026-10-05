import json
from pathlib import Path

import pytest
import numpy as np
from types import SimpleNamespace

from app.domain.errors import PredictionValidationError
from app.services.prediction_csv import CSV_NA_VALUES, read_prediction_csv
from app.domain.schemas import ModelManifest
from app.services.prediction_service import PredictionService

CASES = json.loads((Path(__file__).parent / 'fixtures/prediction_csv_cases.json').read_text(encoding='utf-8'))


def test_explicit_na_policy():
    assert CSV_NA_VALUES == CASES['na_values']


@pytest.mark.parametrize('case', CASES['valid'])
def test_same_row_counts_and_missing_policy_as_browser(case):
    frame = read_prediction_csv(case['csv'].encode(), {})
    columns = case['required'] + ([case['truth']] if case['truth'] else [])
    assert len(frame) == case['total']
    assert int(frame[columns].isna().any(axis=1).sum()) == case['dropped']


@pytest.mark.parametrize('csv', CASES['invalid'])
def test_malformed_csv_is_rejected(csv):
    with pytest.raises(PredictionValidationError): read_prediction_csv(csv.encode(), {})


def test_optional_missing_column_is_passed_to_runtime_as_nan():
    manifest = ModelManifest(id='test', name='test', version='1', framework='sklearn',
        problem_type='regression', target='y', author='test', created_at='2026-10-05',
        description='test', model_path=Path('/unused'), features=[{'name': 'x', 'dtype': 'float64'},
        {'name': 'optional', 'dtype': 'float64', 'required': False}])
    def predict(frame):
        assert frame['optional'].isna().all()
        return np.ones(len(frame))
    service = PredictionService(SimpleNamespace(get=lambda _: manifest),
        SimpleNamespace(create=lambda _: SimpleNamespace(predict=predict)), SimpleNamespace(add=lambda _: None))
    result = service.predict_csv('test', b'x,extra\n1,\n2,\n', ground_truth_column='')
    assert result.dropped_rows == 0
    assert len(result.csv_content.decode().splitlines()) == 3
