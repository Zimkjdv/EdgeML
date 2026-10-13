"""Original-column permutation importance, independent of model framework."""
import csv
import io
import json
import os
import tempfile
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from pydantic import ValidationError

from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.domain.feature_importance import FeatureImportanceReport
from app.domain.model_catalog import ModelCatalog, ModelRegistry
from app.domain.optimization import PredictorProvider
from app.services.dataset_service import DatasetService
from app.core.config import get_settings
from app.services.training_data import clean_supervised_frame
from app.infrastructure.file_lock import FileLock, child_path


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
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, folder / 'feature_importance.json')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_importance(folder: Path, model_id: str, model_name: str) -> dict:
    """Read a saved snapshot without loading a predictor or its source dataset."""
    path = folder / 'feature_importance.json'
    if path.resolve().parent != folder.resolve():
        raise ImportanceUnavailable('Saved feature importance is outside the model package.')
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        raise ImportanceUnavailable('Feature importance has not been computed or included in this package.') from None
    except (OSError, UnicodeError, ValueError):
        raise ImportanceUnavailable('Saved feature importance cannot be read. Restore or recompute the report.') from None
    try:
        return FeatureImportanceReport.model_validate({**payload, 'model_id': model_id, 'model_name': model_name}).model_dump(mode='json', exclude_none=True)
    except (TypeError, ValidationError):
        raise ImportanceUnavailable('Saved feature importance is invalid. Restore or recompute the report.') from None


def published_package(root: Path, model_id: str, registry: ModelRegistry | None = None) -> tuple[Path | None, str | None]:
    """Resolve canonical IDs including legacy, differently named package folders."""
    if registry is not None:
        entry = next((item for item in registry.list_registry() if item.id == model_id), None)
        return (child_path(root, entry.package_name), entry.status) if entry else (None, None)
    matches = [path.parent for path in root.glob('*/metadata.json')
               if not path.parent.name.startswith('.') and json.loads(path.read_text(encoding='utf-8')).get('id') == model_id]
    if len(matches) > 1:
        raise PredictionValidationError('Multiple published packages share this model ID.')
    return (child_path(root, matches[0].name), None) if matches else (None, None)


def importance_identity(report: dict) -> str:
    return json.dumps({key: value for key, value in report.items()
                       if key not in {'model_id', 'model_name', 'publication', 'published_at'}},
                      sort_keys=True, ensure_ascii=False, allow_nan=False)


def publish_importance(folder: Path, report: dict) -> None:
    snapshot = {key: value for key, value in report.items() if key != 'publication'}
    snapshot['published_at'] = datetime.now(timezone.utc).isoformat()
    save_importance(folder, snapshot)


def importance_csv(report: dict) -> str:
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


class PublishedFeatureImportanceService:
    """Read-only report lookup using the same active catalog IDs as Prediction."""

    def __init__(self, catalog: ModelCatalog):
        self.catalog = catalog

    def get(self, model_id: str) -> dict:
        manifest = self.catalog.get(model_id)
        return read_importance(manifest.model_path, manifest.id, manifest.name)

    @staticmethod
    def csv(report: dict) -> str:
        return importance_csv(report)


class FeatureImportanceService:
    def __init__(self, catalog: ModelCatalog, factory: PredictorProvider, datasets: DatasetService, root: Path,
                 publish_root: Path | None = None, registry: ModelRegistry | None = None):
        self.catalog, self.factory, self.datasets, self.root = catalog, factory, datasets, root.resolve()
        self.publish_root, self.registry = publish_root, registry

    def _folder(self, model_id: str) -> Path:
        folder = child_path(self.root, model_id)
        if model_id.startswith('.') or not (folder / 'record.json').is_file():
            raise ModelNotFoundError('Trained model was not found.')
        return folder

    def get(self, model_id: str) -> dict:
        with self._publication_lock(), self._lock(model_id):
            folder = self._folder(model_id)
            record = json.loads((folder / 'record.json').read_text(encoding='utf-8'))
            return self._report(folder, record)

    def _publication_lock(self):
        return FileLock(self.publish_root / '.publication.lock') if self.publish_root else nullcontext()

    def _lock(self, model_id):
        self._folder(model_id)
        return FileLock(child_path(self.root / '.locks', f'{model_id}.lock'))

    def _report(self, folder, record):
        report = read_importance(folder, record['id'], record['name'])
        if not self.publish_root:
            return report
        state = {'status': 'draft'}
        if record.get('status') == 'published':
            destination, status = published_package(self.publish_root, record['id'], self.registry)
            state = {'status': 'unregistered'} if destination is None else {'status': 'missing', 'registry_status': status}
            if destination:
                try:
                    saved = read_importance(destination, record['id'], record['name'])
                    state.update(status='current' if importance_identity(saved) == importance_identity(report) else 'stale',
                                 published_at=saved.get('published_at'), published_computed_at=saved['computed_at'])
                except ImportanceUnavailable:
                    pass
        report['publication'] = state
        return report

    def compute(self, model_id: str) -> dict:
        with self._publication_lock(), self._lock(model_id):
            return self._compute(model_id)

    def _compute(self, model_id: str) -> dict:
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
        frame = clean_supervised_frame(frame, names, target, settings.get('numeric_imputer', 'median'))
        predictor = self.factory.create(self.catalog.get(model_id))
        report = calculate_importance(predictor.predict, frame[names], frame[target],
                                      record.get('problem_type') == 'classification', dataset_id,
                                      'external_test' if settings.get('test_dataset_id') else 'training',
                                      get_settings().importance_max_samples, get_settings().importance_repeats)
        save_importance(folder, report)
        return self._report(folder, record)

    @staticmethod
    def csv(report: dict) -> str:
        return importance_csv(report)
