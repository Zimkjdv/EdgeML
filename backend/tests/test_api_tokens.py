from fastapi.testclient import TestClient

from app.api.dependencies import get_api_token_service
from app.core.config import get_settings
from app.main import create_app
from app.repositories.api_token import SqliteApiTokenRepository
from app.services.api_token_service import ApiTokenService


def test_api_token_can_be_created_used_listed_and_revoked(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EDGEML_API_TOKEN", "bootstrap-token-123456")
    get_settings.cache_clear()
    service = ApiTokenService(SqliteApiTokenRepository(tmp_path / "api_tokens.sqlite3"))
    app = create_app()
    app.dependency_overrides[get_api_token_service] = lambda: service
    client = TestClient(app)
    bootstrap_headers = {"Authorization": "Bearer bootstrap-token-123456"}

    try:
        created = client.post(
            "/api/auth/tokens",
            headers=bootstrap_headers,
            json={"name": "CI integration", "scopes": ["api", "tokens:manage"]},
        )
        assert created.status_code == 201
        payload = created.json()
        assert payload["token"].startswith("edg_")
        assert payload["status"] == "active"
        assert "token_hash" not in payload

        token_headers = {"X-API-Key": payload["token"]}
        listed = client.get("/api/auth/tokens", headers=bootstrap_headers)
        assert listed.status_code == 200
        assert listed.json()[0]["name"] == "CI integration"
        assert "token" not in listed.json()[0]
        assert client.get("/api/models", headers=token_headers).status_code == 200

        management_only = client.post(
            "/api/auth/tokens",
            headers=bootstrap_headers,
            json={"name": "Token administrator", "scopes": ["tokens:manage"]},
        ).json()
        management_headers = {"Authorization": f"Bearer {management_only['token']}"}
        assert client.get("/api/auth/tokens", headers=management_headers).status_code == 200
        assert client.get("/api/models", headers=management_headers).status_code == 401

        revoked = client.delete(f"/api/auth/tokens/{payload['id']}", headers=bootstrap_headers)
        assert revoked.status_code == 200
        assert revoked.json()["status"] == "revoked"
        assert client.get("/api/models", headers=token_headers).status_code == 401
    finally:
        app.dependency_overrides.clear()
        monkeypatch.delenv("EDGEML_API_TOKEN", raising=False)
        get_settings.cache_clear()
