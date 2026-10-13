from typing import Literal
from pydantic import BaseModel, ConfigDict


class FeatureImportanceRank(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    rank: int
    feature: str
    importance: float
    std: float


class ImportancePublication(BaseModel):
    status: Literal['draft', 'unregistered', 'missing', 'current', 'stale']
    registry_status: Literal['active', 'disabled'] | None = None
    published_at: str | None = None
    published_computed_at: str | None = None


class FeatureImportanceReport(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    model_id: str
    model_name: str
    method: Literal['permutation']
    metric: Literal['accuracy_drop', 'rmse_increase']
    baseline_score: float
    dataset_id: str
    data_source: Literal['training', 'external_test']
    sample_count: int
    total_rows: int
    repeats: int
    seed: int
    computed_at: str
    rankings: list[FeatureImportanceRank]
    published_at: str | None = None
    publication: ImportancePublication | None = None
