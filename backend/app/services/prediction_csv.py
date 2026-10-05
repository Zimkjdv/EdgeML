"""Explicit CSV syntax and NA policy, mirrored by the browser CSV reader."""
import csv
from io import StringIO

import pandas as pd

from app.domain.errors import PredictionValidationError

CSV_NA_VALUES = ['', '#N/A', '#N/A N/A', '#NA', '-1.#IND', '-1.#QNAN', '-NaN', '-nan',
                 '1.#IND', '1.#QNAN', '<NA>', 'N/A', 'NA', 'NULL', 'NaN', 'None', 'n/a', 'nan', 'null']

# The standard reader defaults to 128 KiB per field, below valid upload sizes.
# Set once at import (not per request); HTTP file limits remain authoritative.
csv.field_size_limit(max(csv.field_size_limit(), 100 * 1024 * 1024))


def read_prediction_csv(content: bytes, integer_columns: dict) -> pd.DataFrame:
    try:
        text = content.decode('utf-8-sig')
        # Validate quote placement too; csv.reader alone accepts quotes in bare cells.
        quoted = closed = field_started = False
        i = 0
        while i < len(text):
            char = text[i]
            if quoted:
                if char == '"':
                    if i + 1 < len(text) and text[i + 1] == '"': i += 1
                    else: quoted, closed = False, True
            elif char in ',\r\n': closed = field_started = False
            elif char == '"' and not field_started and not closed: quoted = True
            elif closed or char == '"': raise ValueError('malformed quotes')
            else: field_started = True
            i += 1
        if quoted: raise ValueError('unclosed quoted field')
        lines = StringIO(text, newline='').readlines()
        reader = csv.reader(StringIO(text, newline=''), strict=True)
        records, previous = [], 0
        for row in reader:
            raw = ''.join(lines[previous:reader.line_num])
            previous = reader.line_num
            if not raw.strip(): continue
            records.append(row)
        if len(records) < 2: raise ValueError('headers and data are required')
        headers = records[0]
        if any(not value.strip() for value in headers) or len(set(headers)) != len(headers):
            raise ValueError('headers must be nonempty and unique')
        if any(len(row) != len(headers) for row in records[1:]): raise ValueError('row column count mismatch')
        # Pandas handles numeric inference, while the explicit NA list stays stable.
        return pd.read_csv(StringIO(text), dtype=integer_columns, keep_default_na=False, na_values=CSV_NA_VALUES)
    except (UnicodeError, csv.Error, pd.errors.ParserError, pd.errors.EmptyDataError, ValueError) as exc:
        raise PredictionValidationError(f'Invalid UTF-8 CSV: {exc}') from exc
