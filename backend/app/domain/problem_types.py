"""Canonical problem types with compatibility for legacy model manifests."""
from typing import Annotated, Literal

from pydantic import BeforeValidator


def normalize_problem_type(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('Model problem_type must be a string.')
    value = value.strip().lower()
    if value in {'classification', 'binary_classification', 'multiclass_classification'}:
        return 'classification'
    if value == 'regression':
        return value
    raise ValueError(f'Unsupported model problem_type: {value}.')


ProblemType = Annotated[Literal['regression', 'classification'], BeforeValidator(normalize_problem_type)]
