from typing import Literal

from app.domain.model_catalog import ModelRegistry
from app.domain.schemas import ModelRegistrySummary


class ModelRegistryService:
    def __init__(self, registry: ModelRegistry) -> None:
        self._registry = registry

    def list(self) -> list[ModelRegistrySummary]:
        return self._registry.list_registry()

    def set_status(self, model_id: str, status: Literal["active", "disabled"]) -> ModelRegistrySummary:
        return self._registry.set_status(model_id, status)

    def unregister(self, model_id: str) -> None:
        self._registry.unregister(model_id)
