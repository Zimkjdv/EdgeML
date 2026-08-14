import json
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


def test_list_model_ids() -> None:
    response = client().get("/api/models/ids")

    assert response.status_code == 200
    assert {"house-price-v1", "credit-risk-v1", "customer-churn-v1"}.issubset(set(response.json()))


def test_lookup_model_id_by_name() -> None:
    response = client().get("/api/models/by-name/houseprice")

    assert response.status_code == 200
    assert response.json() == {"name": "houseprice", "id": "house-price-v1"}


def test_lookup_model_id_by_unknown_name_returns_not_found() -> None:
    response = client().get("/api/models/by-name/does-not-exist")

    assert response.status_code == 404


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
    assert "filename*=UTF-8''HousePrice_predictions.csv" in response.headers["content-disposition"]


def test_predict_json_returns_prediction_records() -> None:
    repository = InMemoryPredictionHistoryRepository()
    test_client = client(repository)
    response = test_client.post(
        "/api/predict/json",
        json={
            "model_id": "house-price-v1",
            "source_name": "sales-service",
            "data": [{"Area": 80, "Room": 2, "Age": 15}, {"Area": 120, "Room": 3, "Age": 8}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_id"] == "house-price-v1"
    assert payload["prediction_column"] == "prediction"
    assert len(payload["records"]) == 2
    assert "prediction" in payload["records"][0]
    assert payload["metrics"] == {}
    assert payload["dropped_rows"] == 0
    assert repository.records[0].source_filename == "sales-service"


def test_predict_json_supports_ground_truth_and_drops_incomplete_rows() -> None:
    response = client().post(
        "/api/predict/json",
        json={
            "model_id": "house-price-v1",
            "data": [
                {"Area": 80, "Room": 2, "Age": 10, "Price": 180000},
                {"Area": None, "Room": 3, "Age": 8, "Price": 210000},
                {"Area": 90, "Room": 2, "Age": 8, "Price": 210000},
            ],
            "ground_truth_column": "Price",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["records"]) == 2
    assert payload["dropped_rows"] == 1
    assert {"mae", "rmse", "r2"}.issubset(payload["metrics"])
    assert "prediction_error" in payload["records"][0]


def test_predict_json_rejects_missing_feature() -> None:
    response = client().post(
        "/api/predict/json",
        json={"model_id": "house-price-v1", "data": [{"Area": 80, "Room": 2}]},
    )

    assert response.status_code == 422
    assert "Age" in response.json()["detail"]


def test_predict_json_accepts_legacy_records_alias() -> None:
    response = client().post(
        "/api/predict/json",
        json={"model_id": "house-price-v1", "records": [{"Area": 80, "Room": 2, "Age": 15}]},
    )

    assert response.status_code == 200
    assert len(response.json()["records"]) == 1


def test_predict_rejects_missing_column() -> None:
    response = client().post(
        "/api/predict",
        data={"model_id": "house-price-v1"},
        files={"file": ("input.csv", b"Area,Room\n80,2\n", "text/csv")},
    )
    assert response.status_code == 422
    assert "Age" in response.json()["detail"]


def test_predict_drops_rows_with_missing_feature_values() -> None:
    repository = InMemoryPredictionHistoryRepository()
    test_client = client(repository)
    content = b"Area,Room,Age\n80,2,10\n,3,12\n90,2,8\n"

    response = test_client.post(
        "/api/predict",
        data={"model_id": "house-price-v1"},
        files={"file": ("missing-values.csv", content, "text/csv")},
    )

    assert response.status_code == 200
    assert len(response.text.strip().splitlines()) == 3
    assert repository.records[0].row_count == 2


def test_predict_with_ground_truth_returns_metrics_and_error_column() -> None:
    repository = InMemoryPredictionHistoryRepository()
    test_client = client(repository)
    content = b"Area,Room,Age,Price\n80,2,10,180000\n90,2,8,210000\n"

    response = test_client.post(
        "/api/predict",
        data={"model_id": "house-price-v1", "ground_truth_column": "Price"},
        files={"file": ("scored.csv", content, "text/csv")},
    )

    assert response.status_code == 200
    metrics = json.loads(response.headers["x-prediction-metrics"])
    assert {"mae", "mape", "rmse", "max_error", "r2", "pearson_r"}.issubset(metrics)
    assert response.headers["x-prediction-ground-truth"] == "Price"
    assert "prediction_error" in response.text
    assert repository.records[0].row_count == 2


def test_regression_prediction_values_are_rounded_to_four_decimals() -> None:
    content = b"Area,Room,Age\n80,2,10\n90,2,8\n"

    response = client().post(
        "/api/predict",
        data={"model_id": "house-price-v1"},
        files={"file": ("prediction.csv", content, "text/csv")},
    )

    assert response.status_code == 200
    prediction_values = [line.split(",")[-1] for line in response.text.strip().splitlines()[1:]]
    assert all(len(value.split(".")[1]) <= 4 for value in prediction_values if "." in value)


def test_predict_auto_detects_manifest_target() -> None:
    content = b"Area,Room,Age,Price\n80,2,10,180000\n90,2,8,210000\n"

    response = client().post(
        "/api/predict",
        data={"model_id": "house-price-v1"},
        files={"file": ("scored.csv", content, "text/csv")},
    )

    assert response.status_code == 200
    assert response.headers["x-prediction-ground-truth"] == "Price"


def test_empty_ground_truth_value_disables_auto_evaluation() -> None:
    content = b"Area,Room,Age,Price\n80,2,10,180000\n90,2,8,210000\n"

    response = client().post(
        "/api/predict",
        data={"model_id": "house-price-v1", "ground_truth_column": ""},
        files={"file": ("prediction-only.csv", content, "text/csv")},
    )

    assert response.status_code == 200
    assert response.headers["x-prediction-metrics"] == "{}"
    assert response.headers["x-prediction-ground-truth"] == ""
    assert "prediction_error" not in response.text


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
