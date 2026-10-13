"""Dataset identifiers are canonical UUIDs, never filesystem paths."""
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator


def validate_dataset_id(value: str) -> str:
    try:
        canonical = str(UUID(value))
    except (ValueError, AttributeError) as exc:
        raise ValueError("Dataset ID must be a canonical UUID.") from exc
    if value != canonical:
        raise ValueError("Dataset ID must be a canonical UUID.")
    return value


DatasetIdentifier = Annotated[str, AfterValidator(validate_dataset_id)]
