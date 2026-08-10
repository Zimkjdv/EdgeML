from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.core.config import get_settings
from app.core.observability import REGISTRY_ACTIVE
from app.infrastructure.file_model_registry import FileModelRegistry

router = APIRouter()


def _directory_check(path: Path) -> str:
    if path.exists() and path.is_dir():
        return "ok"
    return "missing"


@router.get("/health", tags=["health"])
@router.get("/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", tags=["health"])
def readiness(response: Response) -> dict[str, object]:
    settings = get_settings()
    checks: dict[str, str] = {
        "models": _directory_check(settings.models_root),
        "datasets": _directory_check(settings.datasets_root),
        "trained_models": _directory_check(settings.trained_models_root),
        "registry": "ok",
    }
    try:
        # Listing also validates the JSON index and performs the v0.5 bootstrap if needed.
        registry = FileModelRegistry(settings.model_registry_file, settings.models_root)
        REGISTRY_ACTIVE.set(len(registry.list()))
    except Exception:
        checks["registry"] = "error"

    ready = all(value == "ok" for value in checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if ready else "not_ready", "checks": checks}


@router.get("/metrics", tags=["health"])
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
