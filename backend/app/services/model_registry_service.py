from typing import Callable, Literal

from app.domain.model_catalog import ModelRegistry
from app.domain.schemas import ModelRegistrySummary


class ModelRegistryService:
    def __init__(self, registry: ModelRegistry, invalidate_runtime: Callable[[str], None] | None = None) -> None:
        self._registry = registry
        self._invalidate_runtime = invalidate_runtime

    def list(self) -> list[ModelRegistrySummary]:
        return self._registry.list_registry()

    def set_status(self, model_id: str, status: Literal["active", "disabled"]) -> ModelRegistrySummary:
        result = self._registry.set_status(model_id, status)
        if self._invalidate_runtime: self._invalidate_runtime(model_id)
        return result

    def unregister(self, model_id: str) -> None:
        self._registry.unregister(model_id)
        if self._invalidate_runtime: self._invalidate_runtime(model_id)
