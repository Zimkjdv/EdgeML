"""Positionally paired regression metrics shared by training and prediction."""
import numpy as np
from sklearn.metrics import mean_absolute_error, max_error, r2_score, root_mean_squared_error

from app.domain.errors import PredictionValidationError


def regression_metrics(actual, predicted) -> dict[str, float | None]:
    y = np.asarray(actual, dtype=float).reshape(-1)
    p = np.asarray(predicted, dtype=float).reshape(-1)
    if not y.size or y.shape != p.shape or not np.isfinite(y).all() or not np.isfinite(p).all():
        raise PredictionValidationError('Regression evaluation requires equally sized, nonempty finite values.')
    value_range = float(np.ptp(y))
    rmse = float(root_mean_squared_error(y, p))
    variable_target = value_range > 0
    correlation = float(np.corrcoef(y, p)[0, 1]) if y.size >= 2 and variable_target and np.ptp(p) > 0 else None
    # Do not silently exclude zero targets or substitute epsilon denominators.
    mape = float(np.mean(np.abs((y - p) / y)) * 100) if np.all(y != 0) else None
    values = {
        'mae': float(mean_absolute_error(y, p)),
        'mape': mape,
        'rmse': rmse,
        'nrmse': rmse / value_range if variable_target else None,
        'max_error': float(max_error(y, p)),
        'target_mean': float(np.mean(y)),
        'pearson_r': correlation,
        'r2': float(r2_score(y, p)) if y.size >= 2 and variable_target else None,
    }
    return {key: round(value, 6) if value is not None and np.isfinite(value) else None for key, value in values.items()}
