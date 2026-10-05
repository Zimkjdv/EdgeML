"""One fitted estimator per fold supplies scores, predictions and probabilities."""
from dataclasses import dataclass

import numpy as np
from sklearn.base import clone
from sklearn.metrics import (accuracy_score, f1_score, mean_absolute_error, precision_score,
                             r2_score, recall_score, root_mean_squared_error)

from app.domain.errors import PredictionValidationError


@dataclass
class ValidationResult:
    indices: np.ndarray
    predictions: np.ndarray
    scores: dict[str, np.ndarray]
    probabilities: np.ndarray | None


def evaluate_folds(pipeline, features, target, splits, classification=False, progress=None):
    classes = np.sort(target.unique()) if classification else None
    binary = classification and len(classes) == 2
    indices, predictions, probabilities = [], [], []
    scores = {key: [] for key in (('accuracy', 'f1', 'precision', 'recall') if classification else ('rmse', 'mae', 'r2'))}
    for fold, (train, test) in enumerate(splits, 1):
        if classification and set(target.iloc[train].unique()) != set(classes):
            raise PredictionValidationError("每個驗證訓練折都必須包含全部目標類別；請調整時間／批次切分。")
        estimator = clone(pipeline)
        estimator.fit(features.iloc[train], target.iloc[train])
        predicted = estimator.predict(features.iloc[test])
        actual = target.iloc[test]
        indices.append(test)
        predictions.append(predicted)
        if classification:
            values = {'accuracy': accuracy_score(actual, predicted),
                      'f1': f1_score(actual, predicted, average='weighted', zero_division=0),
                      'precision': precision_score(actual, predicted, average='weighted', zero_division=0),
                      'recall': recall_score(actual, predicted, average='weighted', zero_division=0)}
            if binary:
                probabilities.append(estimator.predict_proba(features.iloc[test])[:, list(estimator.classes_).index(classes[1])])
        else:
            values = {'rmse': -root_mean_squared_error(actual, predicted),
                      'mae': -mean_absolute_error(actual, predicted), 'r2': r2_score(actual, predicted)}
        for key, value in values.items(): scores[key].append(value)
        if progress: progress(fold, len(splits))
    positions = np.concatenate(indices)
    order = np.argsort(positions)
    return ValidationResult(positions[order], np.concatenate(predictions)[order],
        {f'test_{key}': np.asarray(values) for key, values in scores.items()},
        np.concatenate(probabilities)[order] if binary else None)
