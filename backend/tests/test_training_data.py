import json

import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_training_service
from app.domain.errors import PredictionValidationError
from app.domain.training_schemas import TrainingRequest
from app.infrastructure.predictor_factory import PredictorFactory
from app.infrastructure.trained_model_catalog import TrainedModelCatalog
from app.main import create_app
from app.services.feature_importance_service import FeatureImportanceService
from app.services.regression_metrics import regression_metrics
from test_training_algorithms import make_service


def request(dataset_id, **overrides):
    return TrainingRequest(**dict(dataset_id=dataset_id, model_name='缺值清理測試',
        target_column='目標', feature_columns=['數值', '類別'], algorithm='random_forest',
        numeric_imputer='drop', cv_folds=2, hyperparameters={'n_estimators': 5}) | overrides)


@pytest.mark.parametrize('imputer', ['drop', 'median'])
def test_training_and_both_external_evaluation_paths_use_same_rows(tmp_path, imputer):
    datasets, service = make_service(tmp_path)
    frame = pd.DataFrame({'數值': list(range(12)), '類別': ['甲', '乙'] * 6,
                          '目標': np.arange(12) * 2.0, '未選欄位': [np.nan] * 12})
    frame.loc[2, '數值'] = np.nan
    frame.loc[3, '類別'] = None
    frame.loc[4, '目標'] = np.nan
    data = datasets.upload('中文.csv', frame.to_csv(index=False).encode())
    model = service.train(request(data.id, numeric_imputer=imputer, test_dataset_id=data.id))
    # Compute the expected result directly against the documented row policy.
    subset = ['目標', '數值', '類別'] if imputer == 'drop' else ['目標']
    expected = datasets.frame(data.id).dropna(subset=subset)
    assert len(expected) == (9 if imputer == 'drop' else 11)
    root = tmp_path / 'trained'
    pipeline = joblib.load(root / model.id / 'model.pkl')
    metrics = regression_metrics(expected['目標'], pipeline.predict(expected[['數值', '類別']]))
    assert model.test_metrics == metrics
    assert service.evaluate(model.id, data.id).metrics == metrics
    report = json.loads((root / model.id / 'feature_importance.json').read_text())
    assert report['total_rows'] == len(expected)
    importance = FeatureImportanceService(TrainedModelCatalog(root), PredictorFactory(), datasets, root)
    assert importance.compute(model.id)['total_rows'] == len(expected)
    assert service.get(model.id).test_metrics == metrics


@pytest.mark.parametrize('classification', [False, True])
def test_cv_counts_are_checked_after_feature_missing_rows_drop(tmp_path, classification):
    datasets, service = make_service(tmp_path)
    frame = pd.DataFrame({'數值': [1, 2, 3, np.nan, np.nan, np.nan], '類別': ['甲'] * 6,
                          '目標': ['A', 'A', 'B', 'A', 'B', 'B'] if classification else range(6)})
    dataset = datasets.upload('short.csv', frame.to_csv(index=False).encode())
    options = {'problem_type': 'classification', 'algorithm': 'random_forest_classifier'} if classification else {'cv_folds': 4}
    with pytest.raises(PredictionValidationError, match='交叉驗證'):
        service.train(request(dataset.id, **options))
    assert list((tmp_path / 'trained').iterdir()) == []


def test_all_rows_dropped_returns_validation_error_in_training(tmp_path):
    datasets, service = make_service(tmp_path)
    dataset = datasets.upload('empty.csv', '數值,類別,目標\n,甲,1\n,乙,2\n'.encode())
    with pytest.raises(PredictionValidationError, match='沒有可用資料'):
        service.train(request(dataset.id))


def test_empty_external_evaluation_is_422_and_preserves_previous_metrics(tmp_path):
    datasets, service = make_service(tmp_path)
    training = datasets.upload('train.csv', '數值,類別,目標\n1,甲,2\n2,乙,4\n3,甲,6\n4,乙,8\n'.encode())
    empty = datasets.upload('empty.csv', '數值,類別,目標\n,甲,1\n,乙,2\n'.encode())
    model = service.train(request(training.id, test_dataset_id=training.id))
    record_path = tmp_path / 'trained' / model.id / 'record.json'
    before = record_path.read_bytes()
    app = create_app()
    app.dependency_overrides[get_training_service] = lambda: service
    response = TestClient(app).post(f'/api/trained-models/{model.id}/evaluate', json={'dataset_id': empty.id})
    assert response.status_code == 422
    assert '沒有可用資料' in response.json()['detail']
    assert record_path.read_bytes() == before
    with pytest.raises(PredictionValidationError, match='沒有可用資料'):
        service.train(request(training.id, test_dataset_id=empty.id))
