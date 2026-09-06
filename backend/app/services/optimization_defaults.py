import json
from pathlib import Path
from app.domain.feature_defaults import summarize_features
from app.domain.schemas import ModelManifest
from app.domain.errors import ModelNotFoundError


class OptimizationDefaults:
    def __init__(self, trained_root: Path, datasets):
        self.root = trained_root.resolve()
        self.datasets = datasets

    def get(self, manifest: ModelManifest) -> dict:
        if manifest.feature_defaults:
            return {'origin': 'training_snapshot', 'dataset_id': manifest.training_dataset_id, 'features': manifest.feature_defaults}
        folder = (self.root / manifest.id).resolve()
        settings = {}
        if folder.parent == self.root and (folder/'record.json').is_file():
            record = json.loads((folder/'record.json').read_text(encoding='utf-8'))
            snapshot = record.get('manifest', {}).get('feature_defaults')
            if snapshot:
                return {'origin':'training_snapshot', 'dataset_id':record.get('settings', {}).get('dataset_id'), 'features':snapshot}
            settings = record.get('settings', {})
        dataset_id = manifest.training_dataset_id or settings.get('dataset_id')
        # IDs from metadata are still constrained before accessing dataset paths.
        if not dataset_id or Path(dataset_id).name != dataset_id or '/' in dataset_id or '\\' in dataset_id:
            return {'origin':'unavailable', 'dataset_id':None, 'features':{}}
        try:
            frame = self.datasets.frame(dataset_id)
        except (ModelNotFoundError, FileNotFoundError):
            return {'origin':'unavailable', 'dataset_id':dataset_id, 'features':{}}
        if manifest.target in frame:
            frame = frame.dropna(subset=[manifest.target])
        names = [f.name for f in manifest.features]
        if not set(names).issubset(frame.columns):
            return {'origin':'unavailable', 'dataset_id':dataset_id, 'features':{}}
        if settings.get('numeric_imputer') == 'drop':
            frame = frame.dropna(subset=names)
        return {'origin':'source_dataset', 'dataset_id':dataset_id, 'features':summarize_features(frame[names])}
