from __future__ import annotations

import json
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from uuid import uuid4

import pandas as pd
import numpy as np

from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.domain.dataset_identifiers import validate_dataset_id
from app.domain.training_schemas import ColumnProfile, DatasetDetail, DatasetSummary
from app.infrastructure.file_lock import child_path
from app.infrastructure.atomic_json import write_json_atomic
from app.services.prediction_csv import read_csv_text


class DatasetService:
    def __init__(self, datasets_root: Path) -> None:
        self._root = datasets_root
        self._root.mkdir(parents=True, exist_ok=True)

    def upload(self, filename: str, content: bytes) -> DatasetDetail:
        frame = self.read_csv(content)
        dataset_id = str(uuid4())
        now = datetime.now(timezone.utc)
        metadata = {
            "id": dataset_id,
            "name": Path(filename).stem,
            "original_filename": filename,
            "row_count": len(frame),
            "column_count": len(frame.columns),
            "created_at": now.isoformat(),
            "columns": [item.model_dump() for item in self._profile(frame)],
        }
        detail = DatasetDetail.model_validate(metadata)
        # Validate the complete response before making either file visible.
        json.dumps(metadata, ensure_ascii=False, allow_nan=False)
        csv_path, metadata_path = self._paths(dataset_id)
        stream = csv_path.open('xb')
        try:
            with stream:
                stream.write(content)
            write_json_atomic(metadata_path, metadata)
        except Exception:
            csv_path.unlink(missing_ok=True)
            raise
        return detail

    def list(self) -> list[DatasetSummary]:
        summaries = []
        for path in self._root.glob("*.json"):
            try:
                summaries.append(DatasetSummary.model_validate(self.get(path.stem).model_dump()))
            except (ModelNotFoundError, PredictionValidationError):
                # Never follow an invalid filename or linked dataset when listing.
                continue
        return sorted(
            summaries,
            key=lambda item: item.created_at,
            reverse=True,
        )

    def get(self, dataset_id: str) -> DatasetDetail:
        _, path = self._paths(dataset_id)
        if not path.exists():
            raise ModelNotFoundError(f"Dataset '{dataset_id}' was not found.")
        detail = DatasetDetail.model_validate(self._read_metadata(path))
        if detail.id != dataset_id:
            raise PredictionValidationError("Dataset metadata ID does not match its filename.")
        return detail

    def rename(self, dataset_id: str, name: str) -> DatasetDetail:
        self.get(dataset_id)
        _, path = self._paths(dataset_id)
        payload = self._read_metadata(path)
        payload["name"] = name.strip()
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return DatasetDetail.model_validate(payload)

    def delete(self, dataset_id: str) -> None:
        self.get(dataset_id)
        for path in self._paths(dataset_id):
            if path.exists(): path.unlink()

    def frame(self, dataset_id: str) -> pd.DataFrame:
        self.get(dataset_id)
        csv_path, _ = self._paths(dataset_id)
        return self.read_csv(csv_path.read_bytes())

    def _paths(self, dataset_id: str) -> tuple[Path, Path]:
        try:
            validate_dataset_id(dataset_id)
        except ValueError as exc:
            raise PredictionValidationError(str(exc)) from exc
        # Check both files before any operation, including deletion. A linked
        # CSV must not be read even when the JSON metadata itself is safe.
        return (child_path(self._root, f"{dataset_id}.csv"),
                child_path(self._root, f"{dataset_id}.json"))

    @staticmethod
    def read_csv(content: bytes) -> pd.DataFrame:
        for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
            try:
                text = content.decode(encoding)
            except UnicodeDecodeError:
                continue
            # Encoding fallback applies only to decoding, never syntax errors.
            return read_csv_text(text)
        raise PredictionValidationError("CSV 無法以 UTF-8、CP950 或 Big5 編碼讀取。")

    @staticmethod
    def _read_metadata(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _profile(frame: pd.DataFrame) -> list[ColumnProfile]:
        profiles: list[ColumnProfile] = []
        for name in frame.columns:
            series = frame[name]
            missing = int(series.isna().sum())
            numeric = pd.api.types.is_numeric_dtype(series)
            mode = series.dropna().mode()
            base = {
                "name": str(name),
                "raw_dtype": str(series.dtype),
                "ml_type": "numeric" if numeric else "categorical",
                "missing_count": missing,
                "missing_rate": round(missing / max(len(series), 1), 4),
                "unique_count": int(series.nunique(dropna=True)),
                "mode": None if mode.empty else str(mode.iloc[0]),
            }
            if numeric:
                clean = series.dropna()
                if not np.isfinite(clean.to_numpy(dtype=float)).all():
                    raise PredictionValidationError(f"欄位 '{name}' 含有非有限數值（Infinity）。")
                # Scale intermediate calculations to avoid overflow for finite
                # extreme values. Undefined/unrepresentable stats become null.
                scale = max(abs(float(clean.min())), abs(float(clean.max()))) if not clean.empty else 1.0
                scale = scale or 1.0
                normalized = clean / scale
                q1, q3 = normalized.quantile([0.25, 0.75]) if not clean.empty else (0.0, 0.0)
                iqr = q3 - q1
                outliers = int(((normalized < q1 - 1.5 * iqr) | (normalized > q3 + 1.5 * iqr)).sum())
                base.update({
                    "outlier_count": outliers,
                    "minimum": None if clean.empty else float(clean.min()),
                    "maximum": None if clean.empty else float(clean.max()),
                    "mean": None if clean.empty else DatasetService._finite_stat(normalized.mean(), scale),
                    "std": (None if clean.empty else DatasetService._finite_stat(normalized.std(), scale)
                            if len(clean) > 1 else 0.0),
                    "median": None if clean.empty else DatasetService._finite_stat(normalized.median(), scale),
                })
            profiles.append(ColumnProfile(**base))
        return profiles

    @staticmethod
    def _finite_stat(value, scale: float = 1.0) -> float | None:
        number = float(value) * scale
        return number if isfinite(number) else None
