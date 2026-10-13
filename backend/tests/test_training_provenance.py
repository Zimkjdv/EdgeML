import hashlib
import json
import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from fastapi.testclient import TestClient

from app.api.dependencies import get_dataset_service
from app.domain.errors import PredictionValidationError
from app.domain.schemas import ModelManifest
from app.domain.training_schemas import TrainingRequest
from app.main import create_app
from app.services.classification_evaluation import classification_confusion
from app.services.training_provenance import positions_hash
from app.services.validation_strategy import validation_splits
from test_training_algorithms import make_service


@pytest.mark.parametrize('strategy', ['random', 'time', 'group'])
def test_provenance_records_actual_csv_params_runtime_and_original_split_positions(tmp_path, strategy):
    datasets, service = make_service(tmp_path)
    frame = pd.DataFrame({'數值': range(36), '時間': list(reversed(range(36))), '批次': np.repeat(range(6), 6), '目標': np.arange(36) * 2.0})
    frame.loc[4, '目標'] = np.nan
    content = frame.to_csv(index=False).encode('utf-8-sig')
    dataset = datasets.upload('資料.csv', content)
    datasets.rename(dataset.id, '新名稱')
    request = TrainingRequest(dataset_id=dataset.id, model_name='追溯測試', feature_columns=['數值'], target_column='目標',
        algorithm='random_forest', cv_folds=3, validation_strategy=strategy,
        validation_column={'random': None, 'time': '時間', 'group': '批次'}[strategy], hyperparameters={'n_estimators': 5})
    model = service.train(request)
    audit = model.provenance
    assert audit.data[0].sha256 == hashlib.sha256(content).hexdigest()
    assert audit.data[0].name == '新名稱' and audit.data[0].input_rows == 36
    assert audit.resolved_parameters['model__n_estimators'] == 5
    assert audit.resolved_parameters['model__random_state'] == 42
    assert audit.resolved_parameters['model__max_depth'] is None
    assert audit.runtime['python'].startswith('3.') and audit.runtime['scikit-learn']
    parsed = datasets.frame(dataset.id).dropna(subset=['目標'])
    ordered, splits = validation_splits(parsed, request)
    assert audit.validation['row_order_sha256'] == positions_hash(ordered.index)
    for saved, (train, test) in zip(audit.validation['folds'], splits):
        assert saved['train_indices_sha256'] == positions_hash(ordered.index.take(train))
        assert saved['validation_indices_sha256'] == positions_hash(ordered.index.take(test))
        assert not set(train) & set(test)
    assert audit.validation['usable_rows'] == 35
    assert audit.validation['evaluated_rows'] == model.validation_context['evaluated_rows']
    service.publish(model.id)
    metadata = json.loads((tmp_path / 'models' / model.id / 'metadata.json').read_text(encoding='utf-8'))
    manifest = ModelManifest.model_validate({**metadata, 'model_path': tmp_path / 'models' / model.id})
    assert manifest.provenance == audit


def test_xgboost_resolved_booster_config_and_legacy_absence(tmp_path):
    datasets, service = make_service(tmp_path)
    data = datasets.upload('xgb.csv', b'x,target\n' + b''.join(f'{i},{i*2}\n'.encode() for i in range(16)))
    model = service.train(TrainingRequest(dataset_id=data.id, model_name='XGB audit', feature_columns=['x'], target_column='target',
        algorithm='xgboost', cv_folds=2, hyperparameters={'n_estimators': 3}))
    config = model.provenance.resolved_parameters['fitted_booster_config']
    assert config['learner']['learner_train_param']['objective'] == 'reg:squarederror'
    path = tmp_path / 'trained' / model.id / 'record.json'
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload.pop('provenance')
    path.write_text(json.dumps(payload), encoding='utf-8')
    assert service.get(model.id).provenance is None


@pytest.mark.parametrize('labels', [['不合格', '合格'], [0, 1], [False, True], ['甲', '乙', '丙']])
def test_training_and_later_evaluation_confusion_match_scores_with_explicit_order(tmp_path, labels):
    datasets, service = make_service(tmp_path)
    frame = pd.DataFrame({'類別': [f'類別{value}' for value in labels] * 12, '目標': labels * 12})
    csv = frame.to_csv(index=False).encode('utf-8-sig')
    data = datasets.upload('class.csv', csv)
    model = service.train(TrainingRequest(dataset_id=data.id, test_dataset_id=data.id, model_name='分類矩陣',
        target_column='目標', feature_columns=['類別'], problem_type='classification', algorithm='random_forest_classifier',
        cv_folds=5, hyperparameters={'n_estimators': 5}))
    for matrix in (model.validation_confusion, model.test_confusion):
        assert sum(map(sum, matrix.matrix)) == len(frame)
        assert matrix.sample_count == len(frame)
        assert matrix.labels == sorted(labels)
    assert model.validation_metrics['accuracy'] == np.trace(model.validation_confusion.matrix) / len(frame)
    assert 'cv_accuracy_mean' in model.validation_metrics
    prior = model.validation_confusion.model_dump()
    result = service.evaluate_csv(model.id, csv, '外部測試.csv')
    assert result.context.sha256 == hashlib.sha256(csv).hexdigest()
    assert result.confusion == model.test_confusion
    assert service.get(model.id).validation_confusion.model_dump() == prior
    summary = next(item for item in service.list() if item.id == model.id)
    assert summary.test_accuracy == result.metrics['accuracy'] and summary.validation_f1 == model.validation_metrics['f1']


def test_confusion_label_order_binary_unknown_classes_and_bounds():
    actual, predicted = ['合格', '不合格', '合格', '不合格'], ['合格', '合格', '不合格', '不合格']
    report = classification_confusion(actual, predicted, ['不合格', '合格'])
    assert report.matrix == confusion_matrix(actual, predicted, labels=report.labels).tolist()
    assert report.binary == {'negative_label': '不合格', 'positive_label': '合格', 'tn': 1, 'fp': 1, 'fn': 1, 'tp': 1}
    unknown = classification_confusion(['未知', '合格'], ['合格', '合格'], ['不合格', '合格'])
    assert unknown.labels == ['不合格', '合格', '未知'] and unknown.binary is None
    with pytest.raises(PredictionValidationError):
        classification_confusion(['未知', '合格'], ['合格', '合格'], ['不合格', '合格'], max_classes=2)
    assert classification_confusion(np.array([0,1]), np.array([0,1], dtype=object), [0,1]).labels == [0,1]


def test_pooled_classification_metrics_not_unweighted_fold_mean():
    from app.services.training_service import TrainingService
    actual, predicted = [0,0,1,1,1], [0,1,1,1,0]
    scores = {f'test_{key}': np.array([0.5, 1.0]) for key in ('accuracy','f1','precision','recall')}
    metrics = TrainingService._classification_metrics(actual, predicted, scores)
    assert metrics['accuracy'] == accuracy_score(actual, predicted)
    assert metrics['f1'] == round(f1_score(actual,predicted,average='weighted'),6)
    assert metrics['cv_accuracy_mean'] == 0.75 and metrics['accuracy'] != metrics['cv_accuracy_mean']


def test_dataset_preview_pages_nulls_bigints_and_auth(tmp_path, monkeypatch):
    datasets, _ = make_service(tmp_path)
    data = datasets.upload('中文.csv', ('名稱,數量\n' + '\n'.join(f'第{i}列,{9007199254740993+i}' for i in range(122)) + '\n缺值,\n').encode())
    page = datasets.preview(data.id, 100, 20)
    assert page.total_rows == 123 and len(page.rows) == 20 and page.rows[0][0] == '第100列'
    assert page.rows[0][1] == str(9007199254740993 + 100)
    # Preview retains exact raw text even for nullable large-integer columns.
    exact = datasets.upload('big.csv', b'x\n9007199254740993\n')
    assert datasets.preview(exact.id).rows[0][0] == '9007199254740993'
    assert datasets.preview(data.id, 122, 20).rows[0][1] is None
    assert not datasets.preview(data.id, 200, 20).rows
    app = create_app(); app.dependency_overrides[get_dataset_service] = lambda: datasets
    client = TestClient(app)
    assert client.get(f'/api/datasets/{data.id}/preview?offset=100&limit=20').json() == page.model_dump(mode='json')
    for query in ('limit=101', 'limit=0', 'offset=-1'):
        assert client.get(f'/api/datasets/{data.id}/preview?{query}').status_code == 422
    assert client.get('/api/datasets/missing/preview').status_code == 422
    assert client.get('/api/datasets/00000000-0000-0000-0000-000000000000/preview').status_code == 404
    from app.core.config import get_settings
    monkeypatch.setenv('EDGEML_ANONYMOUS_API', 'false'); get_settings.cache_clear()
    assert client.get(f'/api/datasets/{data.id}/preview').status_code == 401


def test_training_uses_single_external_snapshot_even_if_file_changes(tmp_path, monkeypatch):
    datasets, service = make_service(tmp_path)
    content = b'x,target\n' + b''.join(f'{i},{i*2}\n'.encode() for i in range(24))
    primary = datasets.upload('train.csv', content)
    external = datasets.upload('test.csv', content)
    original = service._pipeline
    def change_after_snapshot(features, request):
        (tmp_path / 'datasets' / f'{external.id}.csv').write_bytes(content.replace(b',0\n', b',99999\n'))
        return original(features, request)
    monkeypatch.setattr(service, '_pipeline', change_after_snapshot)
    model = service.train(TrainingRequest(dataset_id=primary.id, test_dataset_id=external.id, model_name='Snapshot test',
        feature_columns=['x'], target_column='target', algorithm='random_forest', cv_folds=2, hyperparameters={'n_estimators':5}))
    assert model.provenance.data[1].sha256 == hashlib.sha256(content).hexdigest()
    assert model.test_evaluation.sha256 == model.provenance.data[1].sha256
    assert model.test_metrics['rmse'] < 10
    assert datasets.snapshot(external.id)[1]['sha256'] != model.provenance.data[1].sha256


@pytest.mark.parametrize('payload', [
    {'labels':['甲','乙'],'matrix':[[1]],'sample_count':1},
    {'labels':['甲'],'matrix':[[-1]],'sample_count':1},
    {'labels':['甲'],'matrix':[[2]],'sample_count':1},
    {'labels':[float('nan')],'matrix':[[1]],'sample_count':1},
])
def test_confusion_contract_rejects_invalid_saved_matrix(payload):
    from app.domain.training_provenance import ClassificationConfusion
    from pydantic import ValidationError
    with pytest.raises(ValidationError): ClassificationConfusion.model_validate(payload)


def test_preview_preserves_quoted_text_multiline_and_never_interprets_html(tmp_path):
    datasets, _ = make_service(tmp_path)
    csv = '描述,編號,小數\n"中文\n第二行",0007,1.2300\n"<script>alert(1)</script>",9007199254740993,0\n'
    data = datasets.upload('raw.csv', csv.encode())
    page = datasets.preview(data.id)
    assert page.rows == [['中文\n第二行','0007','1.2300'],['<script>alert(1)</script>','9007199254740993','0']]
