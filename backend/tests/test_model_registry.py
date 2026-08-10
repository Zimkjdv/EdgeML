from pathlib import Path

from fastapi.testclient import TestClient

from app.api.dependencies import get_model_registry_service
from app.infrastructure.file_model_registry import FileModelRegistry
from app.main import create_app
from app.services.model_registry_service import ModelRegistryService


def registry_client(tmp_path) -> TestClient:
    models_root = Path(__file__).resolve().parents[1] / "ml_models"
    registry = FileModelRegistry(tmp_path / "model_registry.json", models_root)
    app = create_app()
    app.dependency_overrides[get_model_registry_service] = lambda: ModelRegistryService(registry)
    return TestClient(app)


def test_registry_lists_bootstrapped_models(tmp_path) -> None:
    response = registry_client(tmp_path).get("/api/model-registry")

    assert response.status_code == 200
    assert {
        "house-price-v1",
        "credit-risk-v1",
        "customer-churn-v1",
    }.issubset({item["id"] for item in response.json()})
    assert next(item for item in response.json() if item["id"] == "house-price-v1")["status"] == "active"


def test_registry_status_controls_prediction_catalog(tmp_path) -> None:
    models_root = Path(__file__).resolve().parents[1] / "ml_models"
    registry = FileModelRegistry(tmp_path / "model_registry.json", models_root)
    assert {
        "house-price-v1",
        "credit-risk-v1",
        "customer-churn-v1",
    }.issubset({item.id for item in registry.list()})

    registry.set_status("house-price-v1", "disabled")

    active_ids = {item.id for item in registry.list()}
    assert "house-price-v1" not in active_ids
    assert {"credit-risk-v1", "customer-churn-v1"}.issubset(active_ids)
    assert next(item for item in registry.list_registry() if item.id == "house-price-v1").status == "disabled"
