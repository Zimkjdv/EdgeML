"""Publish a complete JSON document, preserving the old file on write failure."""
import json
import os
from pathlib import Path
import tempfile


def write_json_atomic(path: Path, payload: dict) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f'.{path.name}-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(payload, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
