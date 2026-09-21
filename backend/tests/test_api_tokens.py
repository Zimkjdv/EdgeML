from fastapi.testclient import TestClient
from datetime import datetime, timedelta, timezone
import pytest

from app.api.dependencies import get_api_token_service
from app.core.config import get_settings
from app.main import create_app
from app.repositories.api_token import SqliteApiTokenRepository
from app.services.api_token_service import ApiTokenService
from app.domain.auth_schemas import ApiTokenCreateRequest


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


def test_unconfigured_api_is_protected_by_default(monkeypatch):
    monkeypatch.delenv('EDGEML_ANONYMOUS_API')
    get_settings.cache_clear()
    client = TestClient(create_app())
    assert client.get('/api/models').status_code == 401
    assert client.get('/api/auth/session').json()['required'] is True
    assert client.get('/health/live').status_code == 200


@pytest.mark.parametrize('terminal_state', ['revoked', 'expired'])
def test_last_managed_token_cannot_reenable_anonymous_access(monkeypatch, terminal_state):
    monkeypatch.setenv('EDGEML_ANONYMOUS_API', 'false')
    get_settings.cache_clear()
    service = get_api_token_service()
    now = datetime.now(timezone.utc)
    created = service.create(ApiTokenCreateRequest(name='last token', scopes=['api'], expires_at=now + timedelta(hours=1)))
    client = TestClient(create_app())
    assert client.get('/api/models', headers={'X-API-Key': created.token}).status_code == 200
    if terminal_state == 'revoked':
        service.revoke(created.id)
    else:
        monkeypatch.setattr('app.repositories.api_token._now', lambda: now + timedelta(hours=2))
    assert not service.has_active_tokens()
    # Recreate the app too: the configured policy survives restart.
    client = TestClient(create_app())
    assert client.get('/api/models').status_code == 401
    assert client.get('/api/models', headers={'X-API-Key': created.token}).status_code == 401
    assert client.get('/api/auth/session').json()['required'] is True


def test_explicit_development_access_is_independent_of_managed_tokens():
    service = get_api_token_service()
    created = service.create(ApiTokenCreateRequest(name='development token', scopes=['api']))
    client = TestClient(create_app())
    assert client.get('/api/models').status_code == 200
    service.revoke(created.id)
    assert client.get('/api/models').status_code == 200
    assert client.get('/api/models', headers={'X-API-Key': created.token}).status_code == 401
