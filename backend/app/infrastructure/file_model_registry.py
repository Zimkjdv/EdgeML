from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Literal

from app.domain.errors import ModelNotFoundError
from app.domain.schemas import ModelManifest, ModelRegistrySummary, ModelSummary


class FileModelRegistry:
    """JSON-backed model registry with filesystem packages as trusted artifacts.

    The registry owns model metadata and lifecycle status; model packages remain
    on disk and are never accepted through an HTTP upload.
    """

    def __init__(self, registry_file: Path, models_root: Path) -> None:
        self._registry_file = registry_file
        self._models_root = models_root
        self._lock = RLock()

    def list(self) -> list[ModelSummary]:
        return [self._summary(self._manifest(entry)) for entry in self._entries() if entry["status"] == "active"]

    def get(self, model_id: str) -> ModelManifest:
        for entry in self._entries():
            if entry["manifest"]["id"] == model_id and entry["status"] == "active":
                return self._manifest(entry)
        raise ModelNotFoundError(f"Model '{model_id}' was not found.")

    def find_id_by_name(self, name: str) -> str:
        normalized_name = name.strip().casefold()
        for entry in self._entries():
            if entry["status"] != "active":
                continue
            manifest = self._manifest(entry)
            if manifest.name.strip().casefold() == normalized_name:
                return manifest.id
        raise ModelNotFoundError(f"Model with name '{name}' was not found.")

    def list_registry(self) -> list[ModelRegistrySummary]:
        entries = [self._registry_summary(entry) for entry in self._entries()]
        return sorted(entries, key=lambda item: item.name.lower())

    def register(self, manifest: ModelManifest, package_name: str | None = None) -> ModelRegistrySummary:
        package = package_name or manifest.model_path.name
        entry = {
            "manifest": manifest.model_dump(mode="json"),
            "package_name": package,
            "status": "active",
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        entries = [item for item in self._entries() if item["manifest"]["id"] != manifest.id]
        entries.append(entry)
        self._write_entries(entries)
        return self._registry_summary(entry)

    def set_status(self, model_id: str, status: Literal["active", "disabled"]) -> ModelRegistrySummary:
        entries = self._entries()
        for entry in entries:
            if entry["manifest"]["id"] == model_id:
                entry["status"] = status
                self._write_entries(entries)
                return self._registry_summary(entry)
        raise ModelNotFoundError(f"Model '{model_id}' was not found.")

    def update_manifest(self, manifest: ModelManifest) -> ModelRegistrySummary:
        entries = self._entries()
        for entry in entries:
            if entry["manifest"]["id"] == manifest.id:
                entry["manifest"] = manifest.model_dump(mode="json")
                self._write_entries(entries)
                return self._registry_summary(entry)
        raise ModelNotFoundError(f"Model '{manifest.id}' was not found.")

    def unregister(self, model_id: str) -> None:
        entries = self._entries()
        remaining = [entry for entry in entries if entry["manifest"]["id"] != model_id]
        if len(remaining) == len(entries):
            raise ModelNotFoundError(f"Model '{model_id}' was not found.")
        self._write_entries(remaining)

    def _entries(self) -> list[dict]:
        with self._lock:
            if self._registry_file.exists():
                payload = json.loads(self._registry_file.read_text(encoding="utf-8"))
                return payload if isinstance(payload, list) else []

            entries = self._bootstrap_entries()
            self._write_entries(entries)
            return entries

    def _bootstrap_entries(self) -> list[dict]:
        entries: list[dict] = []
        for metadata_path in sorted(self._models_root.glob("*/metadata.json")):
            manifest = self._read_manifest(metadata_path)
            entries.append({
                "manifest": manifest.model_dump(mode="json"),
                "package_name": metadata_path.parent.name,
                "status": "active",
                "registered_at": datetime.now(timezone.utc).isoformat(),
            })
        return entries

    def _write_entries(self, entries: list[dict]) -> None:
        self._registry_file.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            temporary = self._registry_file.with_suffix(f"{self._registry_file.suffix}.tmp")
            temporary.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self._registry_file)

    def _manifest(self, entry: dict) -> ModelManifest:
        payload = dict(entry["manifest"])
        payload["model_path"] = self._models_root / entry["package_name"]
        return ModelManifest.model_validate(payload)

    def _registry_summary(self, entry: dict) -> ModelRegistrySummary:
        manifest = self._manifest(entry)
        return ModelRegistrySummary(
            **self._summary(manifest).model_dump(),
            package_name=entry["package_name"],
            status=entry["status"],
            registered_at=entry["registered_at"],
        )

    @staticmethod
    def _summary(manifest: ModelManifest) -> ModelSummary:
        return ModelSummary(
            id=manifest.id,
            name=manifest.name,
            version=manifest.version,
            framework=manifest.framework,
            problem_type=manifest.problem_type,
            target=manifest.target,
            features=manifest.features,
            prediction_column=manifest.prediction_column,
            description=manifest.description,
        )

    @staticmethod
    def _read_manifest(metadata_path: Path) -> ModelManifest:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        payload["model_path"] = metadata_path.parent
        return ModelManifest.model_validate(payload)
