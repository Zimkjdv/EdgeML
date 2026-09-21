"""Validate numeric features without truncation or integer overflow."""
from decimal import Decimal, InvalidOperation

import numpy as np
import pandas as pd

from app.domain.errors import PredictionValidationError


def coerce_numeric_feature(series: pd.Series, dtype_name: str) -> pd.Series:
    message = f"Column '{series.name}' must contain finite {dtype_name} values within its range."
    try:
        declared = pd.api.types.pandas_dtype(dtype_name)
        dtype = np.dtype(getattr(declared, 'numpy_dtype', declared))
        if dtype.kind in 'iu':
            bounds = np.iinfo(dtype)
            values = []
            for value in series:
                if pd.isna(value):
                    values.append(None)
                    continue
                # Decimal avoids float64 rounding at int64/uint64 boundaries.
                number = Decimal(str(value))
                if (not number.is_finite() or number != number.to_integral_value()
                        or number < int(bounds.min) or number > int(bounds.max)):
                    raise ValueError(message)
                values.append(int(number))
            target_dtype = dtype
            if any(value is None for value in values):
                target_dtype = ('UInt' if dtype.kind == 'u' else 'Int') + str(dtype.itemsize * 8)
            return pd.Series(values, index=series.index, name=series.name, dtype=target_dtype)
        if dtype.kind != 'f':
            raise ValueError(message)
        converted = pd.to_numeric(series, errors='coerce')
        if (converted.isna() & series.notna()).any() or not np.isfinite(converted.dropna()).all():
            raise ValueError(message)
        with np.errstate(over='ignore', invalid='ignore'):
            result = converted.astype(dtype)
        if not np.isfinite(result.dropna()).all():
            raise ValueError(message)
        return result
    except (InvalidOperation, ValueError, TypeError, OverflowError) as exc:
        raise PredictionValidationError(message) from exc
