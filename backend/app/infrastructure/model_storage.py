"""Seed a persistent model store without overwriting deployed packages."""
import shutil
import tempfile
from pathlib import Path
from app.infrastructure.file_lock import FileLock, child_path


def initialize_model_storage(settings) -> None:
    source = settings.bundled_models_root
    if source is None or source.resolve() == settings.models_root.resolve():
        return
    root = settings.models_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    with FileLock(root / '.publication.lock'):
        for metadata in sorted(source.glob('*/metadata.json')):
            destination = child_path(root, metadata.parent.name)
            if destination.exists():
                continue  # Persistent packages always take precedence over image seeds.
            temporary = Path(tempfile.mkdtemp(prefix='.seed-', dir=root))
            try:
                shutil.copytree(metadata.parent, temporary, dirs_exist_ok=True)
                temporary.rename(destination)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
