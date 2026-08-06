from datetime import date
from pathlib import Path

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


class PredictionOutput(BaseModel):
    filename: str
    csv_content: bytes

