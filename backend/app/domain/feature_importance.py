from typing import Literal
from pydantic import BaseModel, ConfigDict


class FeatureImportanceRank(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    rank: int
    feature: str
    importance: float
    std: float


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
