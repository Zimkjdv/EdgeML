"""Original-column permutation importance, independent of model framework."""
import csv
import io
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.domain.model_catalog import ModelCatalog
from app.domain.optimization import PredictorProvider
from app.services.dataset_service import DatasetService
from app.core.config import get_settings


class ImportanceUnavailable(Exception):
    pass


def calculate_importance(predict: Callable, features: pd.DataFrame, target: pd.Series,
                         classification: bool, dataset_id: str, source: str,
                         sample_limit: int = 500, repeats: int = 3, seed: int = 42) -> dict:
    if len(features) < 2:
        raise PredictionValidationError('Feature importance requires at least two usable rows.')
    rng = np.random.default_rng(seed)
    positions = rng.choice(len(features), min(sample_limit, len(features)), replace=False)
    sample = features.iloc[positions].reset_index(drop=True)
    actual = target.iloc[positions].to_numpy()
    if not classification:
        actual = actual.astype(float)
        if not np.isfinite(actual).all():
            raise PredictionValidationError('Feature importance requires finite numeric targets.')

    def score(frame):
        predictions = np.asarray(predict(frame)).reshape(-1)
        if predictions.shape != actual.shape:
            raise PredictionValidationError('Unexpected prediction shape for feature importance.')
        if classification:
            return float(np.mean(predictions == actual))
        predictions = predictions.astype(float)
        value = float(np.sqrt(np.mean((predictions - actual) ** 2)))
        if not np.isfinite(value):
            raise PredictionValidationError('Nonfinite predictions in feature importance.')
        return value

    baseline = score(sample)
    rankings = []
    for name in sample.columns:
        deltas = []
        for _ in range(repeats):
            shuffled = sample.copy()
            shuffled[name] = sample[name].iloc[rng.permutation(len(sample))].to_numpy()
            perturbed = score(shuffled)
            deltas.append(baseline - perturbed if classification else perturbed - baseline)
        rankings.append({'feature': str(name), 'importance': float(np.mean(deltas)),
                         'std': float(np.std(deltas))})
    rankings.sort(key=lambda item: -item['importance'])
    for rank, item in enumerate(rankings, 1):
        item['rank'] = rank
    return {'method': 'permutation', 'metric': 'accuracy_drop' if classification else 'rmse_increase',
            'baseline_score': baseline, 'dataset_id': dataset_id, 'data_source': source,
            'sample_count': len(sample), 'total_rows': len(features), 'repeats': repeats, 'seed': seed,
            'computed_at': datetime.now(timezone.utc).isoformat(), 'rankings': rankings}


def save_importance(folder: Path, report: dict):
    # Readers see either the previous complete report or the new complete report.
    descriptor, temporary = tempfile.mkstemp(prefix='importance-', suffix='.tmp', dir=folder)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, allow_nan=False, indent=2)
        os.replace(temporary, folder / 'feature_importance.json')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class FeatureImportanceService:
    def __init__(self, catalog: ModelCatalog, factory: PredictorProvider, datasets: DatasetService, root: Path):
        self.catalog, self.factory, self.datasets, self.root = catalog, factory, datasets, root.resolve()

    def _folder(self, model_id: str) -> Path:
        folder = (self.root / model_id).resolve()
        if folder.parent != self.root or not (folder / 'record.json').is_file():
            raise ModelNotFoundError('Trained model was not found.')
        return folder

    def get(self, model_id: str) -> dict:
        folder = self._folder(model_id)
        path = folder / 'feature_importance.json'
        if not path.is_file():
            raise ImportanceUnavailable('Feature importance has not been computed. Use POST to compute it.')
        record = json.loads((folder / 'record.json').read_text(encoding='utf-8'))
        return {**json.loads(path.read_text(encoding='utf-8')), 'model_id': model_id, 'model_name': record['name']}

    def compute(self, model_id: str) -> dict:
        folder = self._folder(model_id)
        record = json.loads((folder / 'record.json').read_text(encoding='utf-8'))
        settings = record['settings']
        dataset_id = settings.get('test_dataset_id') or settings.get('dataset_id')
        if not dataset_id or Path(dataset_id).name != dataset_id or '\\' in dataset_id:
            raise PredictionValidationError('The source dataset reference is unavailable.')
        frame = self.datasets.frame(dataset_id)
        names, target = record['feature_columns'], record['target_column']
        missing = set([*names, target]) - set(frame.columns)
        if missing:
            raise PredictionValidationError('Missing importance columns: ' + ', '.join(sorted(missing)))
        frame = frame.dropna(subset=[target])
        if settings.get('numeric_imputer') == 'drop':
            frame = frame.dropna(subset=names)
        predictor = self.factory.create(self.catalog.get(model_id))
        report = calculate_importance(predictor.predict, frame[names], frame[target],
                                      record.get('problem_type') == 'classification', dataset_id,
                                      'external_test' if settings.get('test_dataset_id') else 'training',
                                      get_settings().importance_max_samples, get_settings().importance_repeats)
        save_importance(folder, report)
        return self.get(model_id)

    @staticmethod
    def csv(report: dict) -> str:
        stream = io.StringIO()
        fields = ['rank', 'feature', 'importance', 'std', 'model_id', 'method', 'metric', 'data_source', 'dataset_id', 'sample_count', 'repeats', 'seed']
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in report['rankings']:
            row = {key: item.get(key, report.get(key)) for key in fields}
            # Prevent spreadsheet formula execution when opening user-named features.
            for key, value in row.items():
                if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                    row[key] = "'" + value
            writer.writerow(row)
        return '\ufeff' + stream.getvalue()
