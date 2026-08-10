from fastapi.testclient import TestClient

from app.main import create_app


def test_liveness_and_readiness() -> None:
    client = TestClient(create_app())

    live = client.get("/health/live")
    ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json()["status"] == "ok"
    assert all(value == "ok" for value in ready.json()["checks"].values())


def test_health_alias_and_request_id() -> None:
    client = TestClient(create_app())

    response = client.get("/health", headers={"X-Request-ID": "test-request-01"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "test-request-01"


def test_metrics_endpoint_exposes_http_metrics() -> None:
    client = TestClient(create_app())
    client.get("/health/live")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "edgeml_http_requests_total" in response.text
    assert "edgeml_http_request_duration_seconds" in response.text
