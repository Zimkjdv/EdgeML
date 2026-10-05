import numpy as np
import pandas as pd
import pytest
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.model_selection import KFold, StratifiedKFold, cross_val_predict, cross_validate
from sklearn.pipeline import Pipeline

from app.domain.errors import PredictionValidationError
from app.services.cross_validation import evaluate_folds
from test_training_algorithms import make_service
from test_validation_strategy import request


@pytest.mark.parametrize('classification', [False, True])
def test_one_pass_matches_sklearn_scores_and_predictions(classification):
    x = pd.DataFrame({'x': np.arange(18, dtype=float)})
    x.loc[2, 'x'] = np.nan
    y = pd.Series(['甲', '乙'] * 9 if classification else np.arange(18) * 2.)
    estimator = (RandomForestClassifier if classification else RandomForestRegressor)(n_estimators=4, random_state=42)
    pipeline = Pipeline([('impute', SimpleImputer()), ('model', estimator)])
    splits = list((StratifiedKFold if classification else KFold)(3, shuffle=True, random_state=42).split(x, y))
    scoring = {'accuracy': 'accuracy', 'f1': 'f1_weighted', 'precision': 'precision_weighted', 'recall': 'recall_weighted'} if classification else {'rmse': 'neg_root_mean_squared_error', 'mae': 'neg_mean_absolute_error', 'r2': 'r2'}
    expected = cross_validate(pipeline, x, y, cv=splits, scoring=scoring)
    result = evaluate_folds(pipeline, x, y, splits, classification)
    for key in result.scores: np.testing.assert_allclose(result.scores[key], expected[key])
    np.testing.assert_array_equal(result.predictions, cross_val_predict(pipeline, x, y, cv=splits))
    np.testing.assert_array_equal(result.indices, np.arange(len(x)))
    if classification:
        np.testing.assert_allclose(result.probabilities, cross_val_predict(pipeline, x, y, cv=splits, method='predict_proba')[:, 1])


class CountingRegressor(RegressorMixin, BaseEstimator):
    fits = []
    def fit(self, x, y):
        type(self).fits.append((len(x), float(x.mean().iloc[0])))
        self.mean_ = float(y.mean())
        return self
    def predict(self, x): return np.full(len(x), self.mean_)


def test_training_fits_once_per_fold_plus_final_and_preprocessing_stays_in_fold(tmp_path, monkeypatch):
    datasets, service = make_service(tmp_path)
    data = datasets.upload('count.csv', pd.DataFrame({'x': range(12), 'y': range(12)}).to_csv(index=False).encode())
    CountingRegressor.fits = []
    pipeline = Pipeline([('model', CountingRegressor())])
    monkeypatch.setattr(service, '_pipeline', lambda *_: pipeline)
    service.train(request(dataset_id=data.id))
    assert len(CountingRegressor.fits) == 4
    assert [size for size, _ in CountingRegressor.fits] == [8, 8, 8, 12]
    assert any(mean != 5.5 for _, mean in CountingRegressor.fits[:3])


def test_missing_classes_in_temporal_training_fold_are_rejected():
    x = pd.DataFrame({'x': range(6)})
    y = pd.Series(['甲'] * 3 + ['乙'] * 3)
    with pytest.raises(PredictionValidationError, match='全部目標類別'):
        evaluate_folds(RandomForestClassifier(), x, y, [(np.array([0, 1]), np.array([2, 3]))], True)
