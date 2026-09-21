"""The shared row policy for supervised training and external evaluation."""
import pandas as pd

from app.domain.errors import PredictionValidationError


def clean_supervised_frame(frame: pd.DataFrame, features: list[str], target: str,
                           numeric_imputer: str) -> pd.DataFrame:
    missing = [name for name in [*features, target] if name not in frame]
    if missing:
        raise PredictionValidationError('資料集缺少欄位：' + ', '.join(missing))
    # Preserve the existing drop-mode contract: all selected features must be
    # present, including categorical features; unused columns do not affect rows.
    subset = [target, *features] if numeric_imputer == 'drop' else [target]
    cleaned = frame.dropna(subset=subset).copy()
    if cleaned.empty:
        raise PredictionValidationError('清理缺值資料列後，沒有可用資料。')
    return cleaned
