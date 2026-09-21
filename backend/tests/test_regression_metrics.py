import json

import numpy as np
import pandas as pd
import pytest

from app.services.regression_metrics import regression_metrics
from app.services.training_service import TrainingService
from app.services.prediction_service import PredictionService
from app.domain.training_schemas import ExternalEvaluationResult


def test_noncontiguous_indices_are_paired_positionally():
    actual = pd.Series([1., 4., 2., 8.], index=[0, 2, 3, 4])
    predicted = actual.to_numpy()
    assert TrainingService._metrics(actual, predicted)['pearson_r'] == 1
    assert PredictionService._evaluate_predictions('regression', actual, predicted)['pearson_r'] == 1


def test_known_values_and_oof_not_fold_average():
    actual = pd.Series([1., 2., 3.])
    predicted = [2., 2., 2.]
    scores = {'test_rmse': np.array([-10., -20.]), 'test_mae': np.array([-8., -9.]), 'test_r2': np.array([-.5, .5])}
    metrics = TrainingService._regression_metrics(actual, predicted, scores)
    assert metrics['rmse'] == pytest.approx(np.sqrt(2/3), abs=1e-6)
    assert metrics['mae'] == pytest.approx(2/3, abs=1e-6)
    assert metrics['mape'] == pytest.approx(400/9, abs=1e-6)
    assert metrics['nrmse'] == pytest.approx(np.sqrt(2/3)/2, abs=1e-6)
    assert metrics['r2'] == 0
    assert metrics['pearson_r'] is None
    assert metrics['cv_rmse_mean'] == 15
    assert metrics['rmse_std'] == 5


@pytest.mark.parametrize('actual,predicted', [([0., 0.], [1., 2.]), ([2.], [3.])])
def test_undefined_metrics_are_json_null(actual, predicted):
    metrics = regression_metrics(actual, predicted)
    assert metrics['r2'] is None
    assert metrics['nrmse'] is None
    assert metrics['pearson_r'] is None
    json.dumps(metrics, allow_nan=False)
    response = ExternalEvaluationResult(metrics=metrics)
    assert json.loads(response.model_dump_json())['metrics']['r2'] is None


def test_mape_zero_and_near_zero_policy():
    assert regression_metrics([0., 2.], [1., 2.])['mape'] is None
    assert regression_metrics([1e-8, 2.], [1., 2.])['mape'] > 1e6


def test_negative_r2_is_preserved():
    assert regression_metrics([1., 2., 3.], [5., 5., 5.])['r2'] < 0
