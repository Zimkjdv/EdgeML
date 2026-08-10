from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.schemas import FeatureSpec


class ColumnProfile(BaseModel):
    name: str
    raw_dtype: str
    ml_type: Literal["numeric", "categorical"]
    missing_count: int
    missing_rate: float
    unique_count: int
    outlier_count: int | None = None
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None
    std: float | None = None
    median: float | None = None
    mode: str | None = None


class DatasetSummary(BaseModel):
    id: str
    name: str
    original_filename: str
    row_count: int
    column_count: int
    created_at: datetime


class DatasetDetail(DatasetSummary):
    columns: list[ColumnProfile]


class DatasetRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class TrainingRequest(BaseModel):
    dataset_id: str
    model_name: str = Field(min_length=2, max_length=80)
    target_column: str
    feature_columns: list[str] = Field(min_length=1)
    problem_type: Literal["regression", "classification"] = "regression"
    algorithm: Literal[
        "random_forest", "gradient_boosting", "xgboost", "adaboost", "ridge",
        "random_forest_classifier", "gradient_boosting_classifier", "xgboost_classifier", "adaboost_classifier",
    ]
    numeric_imputer: Literal["median", "mean", "most_frequent", "constant", "drop"] = "median"
    categorical_imputer: Literal["most_frequent", "constant"] = "most_frequent"
    numeric_constant: float = 0
    categorical_constant: str = "Missing"
    cv_folds: int = Field(default=5, ge=2, le=10)
    dimension_reduction: Literal["none", "truncated_svd"] = "none"
    svd_components: int = Field(default=10, ge=2, le=100)
    test_dataset_id: str | None = None
    hyperparameters: dict[str, int | float] = Field(default_factory=dict)


class TrainedModelSummary(BaseModel):
    id: str
    name: str
    completed_at: datetime
    target_column: str
    algorithm: str
    problem_type: str = "regression"
    validation_rmse: float | None = None
    validation_r2: float | None = None
    test_rmse: float | None = None
    test_r2: float | None = None
    status: Literal["draft", "published"]


class TrainedModelDetail(TrainedModelSummary):
    feature_columns: list[str]
    validation_metrics: dict[str, float]
    test_metrics: dict[str, float] | None = None
    settings: dict[str, object]
    manifest: dict[str, object]


class TrainingJob(BaseModel):
    id: str
    status: Literal["queued", "running", "completed", "failed"]
    progress: int = Field(ge=0, le=100)
    message: str
    result_model_id: str | None = None
    error: str | None = None


class ExternalEvaluationRequest(BaseModel):
    dataset_id: str


class ExternalEvaluationResult(BaseModel):
    metrics: dict[str, float]


class TrainedModelDeleteRequest(BaseModel):
    model_ids: list[str] = Field(min_length=1)
