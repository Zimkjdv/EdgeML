from typing import Protocol
from pydantic import BaseModel, ConfigDict, Field
from app.domain.schemas import ModelManifest
from app.predictors.base import BasePredictor


class PredictorProvider(Protocol):
    def create(self, manifest: ModelManifest) -> BasePredictor: ...


class ParameterRule(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    name: str = Field(min_length=1, max_length=200)
    optimize: bool = False
    value: float | str | bool | None = None
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = Field(default=None, gt=0)
    choices: list[str] = Field(default_factory=list, max_length=100)


class OptimizationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    model_id: str = Field(min_length=1, max_length=200)
    target: float
    tolerance: float = Field(default=0.01, ge=0)
    count: int = Field(default=3, ge=1, le=5)
    parameters: list[ParameterRule] = Field(min_length=1, max_length=256)
    seed: int = Field(default=42, ge=0, le=2**32-1)


class Recommendation(BaseModel):
    parameters: dict[str, float | str | bool]
    prediction: float
    absolute_error: float
    within_tolerance: bool


class OptimizationResult(BaseModel):
    model_id: str
    model_name: str
    target: float
    tolerance: float
    seed: int
    evaluated: int
    recommendations: list[Recommendation]
    best_error_by_iteration: list[float]
