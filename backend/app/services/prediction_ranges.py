"""Opt-in filtering against the trusted model package's training snapshot.

Never derive bounds from incoming data or a mutable source dataset. Dtype and
finite-number validation remains the prediction service's responsibility.
"""
from decimal import Decimal, InvalidOperation

import pandas as pd

from app.domain.errors import PredictionValidationError
from app.domain.schemas import ModelManifest


def filter_training_ranges(frame: pd.DataFrame, manifest: ModelManifest) -> tuple[pd.DataFrame, int]:
    outside = pd.Series(False, index=frame.index)
    for feature in manifest.features:
        if not feature.dtype.lower().startswith(('float', 'int', 'uint')):
            continue
        bounds = manifest.feature_defaults.get(feature.name, {})
        try:
            low_value, high_value = bounds['minimum'], bounds['maximum']
            if isinstance(low_value, bool) or isinstance(high_value, bool):
                raise ValueError
            low, high = Decimal(str(low_value)), Decimal(str(high_value))
            if not low.is_finite() or not high.is_finite() or low > high:
                raise ValueError
        except (KeyError, InvalidOperation, TypeError, ValueError):
            raise PredictionValidationError(
                f"模型缺少有效的訓練範圍快照：{feature.name}。請重新訓練並發布模型，或停用 training_range_policy。"
            ) from None
        if feature.name not in frame:
            continue  # Missing optional features are left to the preprocessor.
        # Decimal comparison avoids float rounding of exact int64/uint64 inputs.
        outside |= frame[feature.name].map(
            lambda value: False if pd.isna(value) else not low <= Decimal(str(value)) <= high
        ).astype(bool)
    count = int(outside.sum())
    return frame.loc[~outside].copy(), count
