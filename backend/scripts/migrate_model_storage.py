"""Run inside the OLD backend before Compose recreates it (stdlib only).

No overwrites/deletes: retain old packages, fail on conflicting destination files.
Operators must pause API writes during deployment. Supports stopped containers
after the launcher starts their existing image; never imports the old application.
"""
import filecmp
import os
import shutil
import tempfile
from pathlib import Path


def migrate(source: Path, destination: Path) -> int:
    if source.resolve() == destination.resolve():
        return 0
    if not source.is_dir():
        raise RuntimeError(f'Existing model source is missing: {source}')
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    for package in source.iterdir():
        if not package.is_dir() or package.name.startswith('.'):
            continue
        if package.is_symlink():
            raise RuntimeError(f'Refusing linked package: {package.name}')
        target = destination / package.name
        if target.exists():
            files = [p for p in package.rglob('*') if p.is_file()]
            if target.is_symlink() or any(not (target / p.relative_to(package)).is_file()
                    or not filecmp.cmp(p, target / p.relative_to(package), shallow=False) for p in files):
                raise RuntimeError(f'Migration conflict for {package.name}; original files retained. Resolve before deployment.')
            continue
        temporary = Path(tempfile.mkdtemp(prefix='.migrate-', dir=destination))
        try:
            shutil.copytree(package, temporary, dirs_exist_ok=True)
            temporary.rename(target)
            copied += 1
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    return copied


if __name__ == '__main__':
    count = migrate(Path(os.environ.get('EDGEML_MODELS_ROOT', '/app/ml_models')),
                    Path('/app/data/published_models'))
    print(f'Persistent model migration verified; {count} packages copied. Original packages retained.')
