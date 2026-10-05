import numpy as np
import pandas as pd
import pytest

from app.domain.errors import PredictionValidationError
from app.domain.training_schemas import TrainingRequest
from app.services.validation_strategy import validation_splits
from test_training_algorithms import make_service


def request(**kwargs):
    return TrainingRequest(**dict(dataset_id='test', model_name='驗證策略測試', target_column='y',
        feature_columns=['x'], algorithm='random_forest', cv_folds=3,
        hyperparameters={'n_estimators': 3}) | kwargs)


def test_time_splits_sort_and_keep_equal_timestamps_together():
    frame = pd.DataFrame({'time': np.repeat(np.arange(12), 2)[::-1], 'x': range(24), 'y': range(24)})
    ordered, splits = validation_splits(frame, request(validation_strategy='time', validation_column='time', time_gap=1))
    evaluated = []
    for train, test in splits:
        assert ordered.iloc[train].time.max() + 1 < ordered.iloc[test].time.min()
        assert not set(ordered.iloc[train].time) & set(ordered.iloc[test].time)
        evaluated.extend(test)
    assert len(set(evaluated)) == len(evaluated) < len(frame)


def test_groups_do_not_cross_folds():
    frame = pd.DataFrame({'batch': ['甲', '乙', '丙', '丁'] * 3, 'x': range(12), 'y': range(12)})
    ordered, splits = validation_splits(frame, request(validation_strategy='group', validation_column='batch'))
    for train, test in splits:
        assert not set(ordered.iloc[train].batch) & set(ordered.iloc[test].batch)
    assert sorted(np.concatenate([test for _, test in splits])) == list(range(12))


@pytest.mark.parametrize('strategy,column,values', [('group', 'batch', ['甲'] * 12),
    ('time', 'time', ['bad'] * 12), ('time', 'time', [None] * 12), ('time', 'missing', range(12))])
def test_invalid_strategy_data_is_rejected(strategy, column, values):
    frame = pd.DataFrame({'time': values, 'batch': values, 'x': range(12), 'y': range(12)})
    with pytest.raises(PredictionValidationError):
        validation_splits(frame, request(validation_strategy=strategy, validation_column=column))


@pytest.mark.parametrize('strategy', ['time', 'group'])
def test_strategy_training_records_evaluated_coverage(tmp_path, strategy):
    datasets, service = make_service(tmp_path)
    frame = pd.DataFrame({'split': np.repeat(range(12), 2), 'x': range(24), 'y': np.arange(24) * 2.})
    data = datasets.upload('中文.csv', frame.to_csv(index=False).encode())
    model = service.train(request(dataset_id=data.id, validation_strategy=strategy, validation_column='split'))
    assert model.evaluation_version == 'oof-v2'
    assert model.validation_context['evaluated_rows'] == (18 if strategy == 'time' else 24)
    assert model.validation_metrics['pearson_r'] is not None
