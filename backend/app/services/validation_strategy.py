"""Build row-position splits without leaking future rows or batch membership."""
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold, KFold, StratifiedKFold, TimeSeriesSplit

from app.domain.errors import PredictionValidationError
from app.domain.training_schemas import TrainingRequest


def validation_splits(frame: pd.DataFrame, request: TrainingRequest):
    if request.validation_strategy == "random":
        splitter = (StratifiedKFold if request.problem_type == "classification" else KFold)(
            n_splits=request.cv_folds, shuffle=True, random_state=42)
        return frame, list(splitter.split(frame, frame[request.target_column]))
    column = request.validation_column
    if not column or column not in frame or column == request.target_column:
        raise PredictionValidationError("時間／批次驗證必須指定非 target 的有效欄位。")
    if frame[column].isna().any():
        raise PredictionValidationError("驗證排序／批次欄位不可有缺值。")
    try:
        if request.validation_strategy == "group":
            groups = frame[column].astype(str)
            if groups.nunique() < request.cv_folds:
                raise PredictionValidationError("批次數量必須至少等於交叉驗證折數。")
            return frame, list(GroupKFold(request.cv_folds).split(frame, groups=groups))
        values = frame[column]
        order = values if pd.api.types.is_numeric_dtype(values) else pd.to_datetime(values, errors="raise", utc=True)
        if order.isna().any() or (pd.api.types.is_numeric_dtype(order) and not np.isfinite(order).all()):
            raise ValueError("invalid ordering values")
        # Split unique timestamps: equal times always stay on the same side.
        positions = np.argsort(order.to_numpy(), kind="stable")
        sorted_frame = frame.iloc[positions].copy()
        codes, unique = pd.factorize(order.iloc[positions], sort=False)
        splitter = TimeSeriesSplit(n_splits=request.cv_folds, gap=request.time_gap)
        splits = [(np.flatnonzero(np.isin(codes, train)), np.flatnonzero(np.isin(codes, test)))
                  for train, test in splitter.split(unique)]
        return sorted_frame, splits
    except (ValueError, TypeError) as exc:
        raise PredictionValidationError("時間驗證需要可排序的數字或日期時間，且不同時間點數量須足以支援折數與間隔。") from exc
