from __future__ import annotations

from typing import Literal, Protocol

from app.domain.schemas import ModelManifest, ModelRegistrySummary, ModelSummary


class ModelCatalog(Protocol):
    """Application boundary for discovering models available to Prediction."""

    def list(self) -> list[ModelSummary]: ...

    def get(self, model_id: str) -> ModelManifest: ...

    def find_id_by_name(self, name: str) -> str: ...


class ModelRegistry(ModelCatalog, Protocol):
    """Registry operations used by model publication and administration."""

    def list_registry(self) -> list[ModelRegistrySummary]: ...

    def set_status(self, model_id: str, status: Literal["active", "disabled"]) -> ModelRegistrySummary: ...

    def unregister(self, model_id: str) -> None: ...

    def register(self, manifest: ModelManifest, package_name: str | None = None) -> ModelRegistrySummary: ...

    def update_manifest(self, manifest: ModelManifest) -> ModelRegistrySummary: ...
