import math
import pandas as pd


def summarize_features(frame: pd.DataFrame) -> dict:
    """Compact training-time defaults; never serialize NaN or raw rows."""
    result = {}
    for name in frame:
        column = frame[name].dropna()
        numeric = str(frame[name].dtype).startswith(('float', 'int'))
        if numeric:
            column = column[column.map(lambda v: math.isfinite(float(v)))]
            if column.empty:
                continue
            value = float(column.median())
            if str(frame[name].dtype).startswith('int'):
                value = int(column.iloc[(column - value).abs().argmin()])
            result[name] = {'value': value, 'minimum': float(column.min()), 'maximum': float(column.max()), 'choices': []}
        elif not column.empty:
            choices = sorted(set(column.astype(str)))
            result[name] = {'value': str(column.mode().iloc[0]), 'minimum': None, 'maximum': None,
                            'choices': choices[:100], 'choices_truncated': len(choices) > 100}
    return result
