import pytest
from app.api.dependencies import get_api_token_service, get_prediction_service
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def isolated_token_storage(tmp_path, monkeypatch):
    """Tests must not authenticate against or update a developer's real tokens."""
    monkeypatch.delenv('EDGEML_API_TOKEN', raising=False)
    for name in ('EDGEML_WEB_PASSWORD', 'EDGEML_WEB_USERNAME', 'EDGEML_WEB_COOKIE_SECURE', 'EDGEML_WEB_ALLOWED_ORIGINS', 'EDGEML_WEB_SESSION_SECONDS'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('EDGEML_API_TOKENS_DATABASE', str(tmp_path / 'tokens.sqlite3'))
    monkeypatch.setenv('EDGEML_MODEL_REGISTRY_FILE', str(tmp_path / 'model_registry.json'))
    get_settings.cache_clear()
    get_api_token_service.cache_clear()
    get_prediction_service.cache_clear()
    yield
    get_api_token_service.cache_clear()
    get_prediction_service.cache_clear()
    get_settings.cache_clear()
