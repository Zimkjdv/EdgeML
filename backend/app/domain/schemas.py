from datetime import date, datetime
from pathlib import Path

from typing import Literal
from typing import Any

from pydantic import BaseModel, Field, model_validator


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


class JsonPredictionRequest(BaseModel):
    model_id: str = Field(min_length=1)
    data: list[dict[str, Any]] | None = Field(default=None, min_length=1)
    records: list[dict[str, Any]] | None = Field(default=None, min_length=1)
    ground_truth_column: str | None = None
    source_name: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_input_data(self) -> "JsonPredictionRequest":
        if self.data is None and self.records is None:
            raise ValueError("Either 'data' or the legacy 'records' field is required.")
        if self.data is not None and self.records is not None:
            raise ValueError("Send only one of 'data' or 'records'.")
        return self

    @property
    def input_data(self) -> list[dict[str, Any]]:
        return self.data if self.data is not None else self.records or []


class JsonPredictionOutput(BaseModel):
    model_id: str
    model_name: str
    prediction_column: str
    records: list[dict[str, Any]]
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
