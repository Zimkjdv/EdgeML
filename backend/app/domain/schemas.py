from datetime import date, datetime
from pathlib import Path

from typing import Literal

from pydantic import BaseModel, Field


class FeatureSpec(BaseModel):
    name: str
    dtype: str
    required: bool = True


class ModelManifest(BaseModel):
    id: str
    name: str
    version: str
    framework: str
    problem_type: str
    target: str
    features: list[FeatureSpec]
    prediction_column: str = "prediction"
    author: str
    created_at: date
    description: str
    artifact: str = "model.pkl"
    preprocess_artifact: str | None = None
    model_path: Path = Field(exclude=True)


class ModelSummary(BaseModel):
    id: str
    name: str
    version: str
    framework: str
    problem_type: str
    target: str
    features: list[FeatureSpec]
    prediction_column: str
    description: str


class ModelRegistrySummary(ModelSummary):
    package_name: str
    status: Literal["active", "disabled"]
    registered_at: datetime


class PredictionOutput(BaseModel):
    filename: str
    csv_content: bytes
    metrics: dict[str, float] = Field(default_factory=dict)
    ground_truth_column: str | None = None
    dropped_rows: int = 0


class PredictionHistoryRecord(BaseModel):
    id: str
    model_id: str
    model_name: str
    source_filename: str
    row_count: int
    created_at: datetime
