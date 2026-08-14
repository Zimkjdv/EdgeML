import json
from pathlib import Path

from app.domain.errors import ModelNotFoundError
from app.domain.schemas import ModelManifest, ModelSummary


class FileModelCatalog:
    def __init__(self, models_root: Path) -> None:
        self._models_root = models_root

    def list(self) -> list[ModelSummary]:
        manifests = [self._read_manifest(path) for path in self._models_root.glob("*/metadata.json")]
        return [
            ModelSummary(
                id=item.id,
                name=item.name,
                version=item.version,
                framework=item.framework,
                problem_type=item.problem_type,
                target=item.target,
                features=item.features,
                prediction_column=item.prediction_column,
                description=item.description,
            )
            for item in sorted(manifests, key=lambda manifest: manifest.name.lower())
        ]

    def get(self, model_id: str) -> ModelManifest:
        for path in self._models_root.glob("*/metadata.json"):
            manifest = self._read_manifest(path)
            if manifest.id == model_id:
                return manifest
        raise ModelNotFoundError(f"Model '{model_id}' was not found.")

    def find_id_by_name(self, name: str) -> str:
        normalized_name = name.strip().casefold()
        for path in self._models_root.glob("*/metadata.json"):
            manifest = self._read_manifest(path)
            if manifest.name.strip().casefold() == normalized_name:
                return manifest.id
        raise ModelNotFoundError(f"Model with name '{name}' was not found.")

    @staticmethod
    def _read_manifest(metadata_path: Path) -> ModelManifest:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        payload["model_path"] = metadata_path.parent
        return ModelManifest.model_validate(payload)
