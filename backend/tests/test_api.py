from pathlib import Path

from fastapi.testclient import TestClient

from app.api.dependencies import get_prediction_service
from app.main import create_app


def client() -> TestClient:
    get_prediction_service.cache_clear()
    return TestClient(create_app())


def test_list_models() -> None:
    response = client().get("/api/models")
    assert response.status_code == 200
    assert {model["id"] for model in response.json()} == {
        "house-price-v1",
        "credit-risk-v1",
        "customer-churn-v1",
    }


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
