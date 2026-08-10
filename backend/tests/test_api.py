from pathlib import Path

from fastapi.testclient import TestClient

from app.api.dependencies import get_prediction_service
from app.core.config import get_settings
from app.domain.schemas import PredictionHistoryRecord
from app.infrastructure.model_catalog import FileModelCatalog
from app.infrastructure.predictor_factory import PredictorFactory
from app.main import create_app
from app.services.prediction_service import PredictionService


class InMemoryPredictionHistoryRepository:
    def __init__(self) -> None:
        self.records: list[PredictionHistoryRecord] = []

    def add(self, record: PredictionHistoryRecord) -> None:
        self.records.append(record)

    def list(self) -> list[PredictionHistoryRecord]:
        return list(reversed(self.records))


def client(
    history_repository: InMemoryPredictionHistoryRepository | None = None,
) -> TestClient:
    repository = history_repository or InMemoryPredictionHistoryRepository()
    settings = get_settings()
    service = PredictionService(
        catalog=FileModelCatalog(settings.models_root),
        predictor_factory=PredictorFactory(),
        history_repository=repository,
    )
    app = create_app()
    app.dependency_overrides[get_prediction_service] = lambda: service
    return TestClient(app)


def test_list_models() -> None:
    response = client().get("/api/models")
    assert response.status_code == 200
    assert {
        "house-price-v1",
        "credit-risk-v1",
        "customer-churn-v1",
    }.issubset({model["id"] for model in response.json()})


def test_predict_returns_csv() -> None:
    csv_path = Path(__file__).resolve().parents[1] / "sample_data" / "house_price_input.csv"
    response = client().post(
        "/api/predict",
        data={"model_id": "house-price-v1"},
        files={"file": ("input.csv", csv_path.read_bytes(), "text/csv")},
    )
    assert response.status_code == 200
    assert "prediction" in response.text
    assert response.headers["content-type"].startswith("text/csv")


def test_predict_rejects_missing_column() -> None:
    response = client().post(
        "/api/predict",
        data={"model_id": "house-price-v1"},
        files={"file": ("input.csv", b"Area,Room\n80,2\n", "text/csv")},
    )
    assert response.status_code == 422
    assert "Age" in response.json()["detail"]


def test_successful_prediction_is_added_to_history() -> None:
    repository = InMemoryPredictionHistoryRepository()
    test_client = client(repository)
    csv_path = Path(__file__).resolve().parents[1] / "sample_data" / "house_price_input.csv"

    prediction_response = test_client.post(
        "/api/predict",
        data={"model_id": "house-price-v1"},
        files={"file": ("house-input.csv", csv_path.read_bytes(), "text/csv")},
    )
    history_response = test_client.get("/api/prediction-history")

    assert prediction_response.status_code == 200
    assert history_response.status_code == 200
    assert len(history_response.json()) == 1
    record = history_response.json()[0]
    assert record["model_id"] == "house-price-v1"
    assert record["model_name"] == "HousePrice"
    assert record["source_filename"] == "house-input.csv"
    assert record["row_count"] == 4


def test_failed_prediction_is_not_added_to_history() -> None:
    repository = InMemoryPredictionHistoryRepository()
    test_client = client(repository)

    response = test_client.post(
        "/api/predict",
        data={"model_id": "house-price-v1"},
        files={"file": ("invalid.csv", b"Area,Room\n80,2\n", "text/csv")},
    )

    assert response.status_code == 422
    assert repository.records == []


def test_credit_risk_prediction_returns_csv() -> None:
    csv_path = Path(__file__).resolve().parents[1] / "sample_data" / "credit_risk_input.csv"
    response = client().post(
        "/api/predict",
        data={"model_id": "credit-risk-v1"},
        files={"file": ("input.csv", csv_path.read_bytes(), "text/csv")},
    )
    assert response.status_code == 200
    assert "approved_prediction" in response.text


def test_customer_churn_prediction_returns_csv() -> None:
    csv_path = Path(__file__).resolve().parents[1] / "sample_data" / "customer_churn_input.csv"
    response = client().post(
        "/api/predict",
        data={"model_id": "customer-churn-v1"},
        files={"file": ("input.csv", csv_path.read_bytes(), "text/csv")},
    )
    assert response.status_code == 200
    assert "churn_prediction" in response.text
