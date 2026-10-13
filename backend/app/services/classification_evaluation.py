"""One label-order contract for pooled OOF and independent external tests."""
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix

from app.domain.errors import PredictionValidationError
from app.domain.training_provenance import ClassificationConfusion


def classification_confusion(actual, predicted, classes, max_classes=100):
    actual = pd.Series(np.asarray(actual)).infer_objects().to_numpy()
    predicted = pd.Series(np.asarray(predicted)).infer_objects().to_numpy()
    labels = [value.item() if isinstance(value, np.generic) else value for value in classes]
    observed = pd.unique(np.concatenate([actual, predicted])).tolist()
    labels.extend(sorted((value for value in observed if value not in labels), key=lambda value: str(value)))
    if len(labels) > max_classes:
        raise PredictionValidationError(f'Classification supports at most {max_classes} labels in an evaluation.')
    if any(isinstance(value, float) and not np.isfinite(value) for value in labels):
        raise PredictionValidationError('Classification labels must be finite.')
    matrix = confusion_matrix(actual, predicted, labels=labels).tolist()
    binary = None
    if len(labels) == 2:
        binary = {'negative_label': labels[0], 'positive_label': labels[1],
                  'tn': matrix[0][0], 'fp': matrix[0][1], 'fn': matrix[1][0], 'tp': matrix[1][1]}
    return ClassificationConfusion(labels=labels, matrix=matrix, sample_count=len(actual), binary=binary)
