"""Audit metadata only: no credentials, machine paths or fitted training rows."""
import hashlib
import json
import platform
from importlib.metadata import PackageNotFoundError, version
import numpy as np

from app.domain.training_provenance import TrainingProvenance


def json_parameter(value):
    if isinstance(value, np.generic): value = value.item()
    if value is None or isinstance(value, (str, bool, int)): return value
    if isinstance(value, float): return value if np.isfinite(value) else str(value)
    if isinstance(value, dict): return {str(key): json_parameter(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)): return [json_parameter(item) for item in value]
    # Parameter objects are described, never repr()'d with addresses/paths.
    return {'class': f'{type(value).__module__}.{type(value).__qualname__}'}


def positions_hash(indices):
    return hashlib.sha256(json.dumps([int(value) for value in indices], separators=(',', ':')).encode()).hexdigest()


def training_provenance(request, pipeline, frame, splits, datasets, evaluated_rows):
    runtime = {'python': platform.python_version()}
    for package in ('numpy', 'pandas', 'scipy', 'scikit-learn', 'xgboost', 'joblib'):
        try: runtime[package] = version(package)
        except PackageNotFoundError: runtime[package] = None
    fitted = getattr(pipeline, 'pipeline_', pipeline)
    parameters = {key: json_parameter(value) for key, value in fitted.get_params(deep=True).items()}
    model = fitted.named_steps['model']
    if hasattr(model, 'get_booster'):
        # XGBoost's Python None defaults can resolve only after fit; preserve
        # the actual booster configuration, too, including its objective.
        parameters['fitted_booster_config'] = json.loads(model.get_booster().save_config())
    folds = [{'fold': number, 'train_rows': len(train), 'validation_rows': len(test),
              'train_indices_sha256': positions_hash(frame.index.take(train)),
              'validation_indices_sha256': positions_hash(frame.index.take(test))}
             for number, (train, test) in enumerate(splits, 1)]
    return TrainingProvenance(data=datasets, runtime=runtime, resolved_parameters=parameters,
        target_column=request.target_column, feature_columns=request.feature_columns,
        validation={'strategy': request.validation_strategy, 'column': request.validation_column,
                    'time_gap': request.time_gap, 'seed': 42 if request.validation_strategy == 'random' else None,
                    'folds': folds, 'usable_rows': len(frame), 'evaluated_rows': evaluated_rows,
                    'excluded_rows': len(frame) - evaluated_rows, 'row_order_sha256': positions_hash(frame.index),
                    'index_contract': 'zero-based original CSV data-row positions, excluding the header; after cleaning and ordering'})
