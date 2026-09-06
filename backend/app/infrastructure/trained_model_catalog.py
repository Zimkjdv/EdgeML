"""Read-only catalog of trusted, locally trained model artifacts."""
import json
from pathlib import Path
from app.domain.errors import ModelNotFoundError
from app.domain.schemas import ModelManifest, ModelSummary


class TrainedModelCatalog:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def get(self, model_id: str) -> ModelManifest:
        folder = (self.root / model_id).resolve()
        if folder.parent != self.root or not (folder / 'record.json').is_file():
            raise ModelNotFoundError('Trained model was not found.')
        record = json.loads((folder / 'record.json').read_text(encoding='utf-8'))
        return ModelManifest.model_validate({**record['manifest'], 'model_path': folder})

    def list(self) -> list[ModelSummary]:
        return [ModelSummary.model_validate(self.get(p.parent.name).model_dump())
                for p in self.root.glob('*/record.json')]

    def find_id_by_name(self, name: str) -> str:
        for model in self.list():
            if model.name == name:
                return model.id
        raise ModelNotFoundError('Trained model was not found.')
