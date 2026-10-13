from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator


class DatasetFingerprint(BaseModel):
    dataset_id: str
    name: str
    sha256: str
    input_rows: int
    column_count: int
    role: Literal['training', 'external_test']


class TrainingProvenance(BaseModel):
    version: Literal['training-v1'] = 'training-v1'
    data: list[DatasetFingerprint]
    runtime: dict[str, str | None]
    resolved_parameters: dict[str, object]
    validation: dict[str, object]
    target_column: str
    feature_columns: list[str]


class ClassificationConfusion(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    # Labels retain their JSON types; rows=actual, columns=predicted, same order.
    labels: list[StrictStr | StrictInt | StrictFloat | StrictBool]
    matrix: list[list[Annotated[StrictInt, Field(ge=0)]]]
    sample_count: int = Field(ge=1)
    binary: dict[str, object] | None = None

    @model_validator(mode='after')
    def validate_matrix(self):
        size = len(self.labels)
        if not size or len(set(self.labels)) != size or len(self.matrix) != size or any(len(row) != size for row in self.matrix):
            raise ValueError('Confusion labels must be unique and matrix shape must match their order.')
        if sum(map(sum, self.matrix)) != self.sample_count:
            raise ValueError('Confusion counts must sum to sample_count.')
        return self
