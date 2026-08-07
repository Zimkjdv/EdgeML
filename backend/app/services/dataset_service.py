from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pandas as pd

from app.domain.errors import ModelNotFoundError, PredictionValidationError
from app.domain.training_schemas import ColumnProfile, DatasetDetail, DatasetSummary


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
        (self._root / f"{dataset_id}.csv").write_bytes(content)
        (self._root / f"{dataset_id}.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return DatasetDetail.model_validate(metadata)

    def list(self) -> list[DatasetSummary]:
        return sorted(
            [DatasetSummary.model_validate(self._read_metadata(path)) for path in self._root.glob("*.json")],
            key=lambda item: item.created_at,
            reverse=True,
        )

    def get(self, dataset_id: str) -> DatasetDetail:
        path = self._root / f"{dataset_id}.json"
        if not path.exists():
            raise ModelNotFoundError(f"Dataset '{dataset_id}' was not found.")
        return DatasetDetail.model_validate(self._read_metadata(path))

    def rename(self, dataset_id: str, name: str) -> DatasetDetail:
        detail = self.get(dataset_id)
        path = self._root / f"{dataset_id}.json"
        payload = self._read_metadata(path)
        payload["name"] = name.strip()
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return DatasetDetail.model_validate(payload)

    def frame(self, dataset_id: str) -> pd.DataFrame:
        self.get(dataset_id)
        return self.read_csv((self._root / f"{dataset_id}.csv").read_bytes())

    @staticmethod
    def read_csv(content: bytes) -> pd.DataFrame:
        errors: list[Exception] = []
        for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
            try:
                return pd.read_csv(BytesIO(content), encoding=encoding)
            except (UnicodeDecodeError, pd.errors.ParserError) as exc:
                errors.append(exc)
        raise PredictionValidationError("CSV 無法以 UTF-8、CP950 或 Big5 編碼讀取。") from errors[-1]

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
                q1, q3 = clean.quantile([0.25, 0.75]) if not clean.empty else (None, None)
                iqr = q3 - q1 if q1 is not None else 0
                outliers = int(((clean < q1 - 1.5 * iqr) | (clean > q3 + 1.5 * iqr)).sum()) if iqr else 0
                base.update({
                    "outlier_count": outliers,
                    "minimum": None if clean.empty else float(clean.min()),
                    "maximum": None if clean.empty else float(clean.max()),
                    "mean": None if clean.empty else float(clean.mean()),
                    "std": None if clean.empty else float(clean.std()) if len(clean) > 1 else 0.0,
                    "median": None if clean.empty else float(clean.median()),
                })
            profiles.append(ColumnProfile(**base))
        return profiles
