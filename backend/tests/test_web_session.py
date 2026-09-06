import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app
from app.services.web_session_service import digest
from test_api import client as prediction_client


@pytest.fixture
def browser(monkeypatch):
    monkeypatch.setenv('EDGEML_WEB_PASSWORD', 'a-separate-web-password')
    monkeypatch.setenv('EDGEML_API_TOKEN', 'integration-only-token')
    get_settings.cache_clear()
    return prediction_client()


def login(browser, password='a-separate-web-password', **headers):
    return browser.post('/api/auth/session', json={'username': 'admin', 'password': password},
                        headers={'X-EdgeML-Login': '1', **headers})


def test_browser_csv_prediction_and_logout_revoke_session(browser):
    assert browser.get('/api/models').status_code == 401
    assert browser.post('/api/predict').status_code == 401
    result = login(browser)
    assert result.status_code == 200
    cookie = result.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=strict' in cookie and 'path=/api' in cookie
    raw = browser.cookies.get('edgeml_session')
    csrf = result.json()['csrf_token']
    assert browser.get('/api/auth/session').json()['csrf_token'] == csrf
    assert browser.get('/api/models').status_code == 200
    params = {'data': {'model_id': 'house-price-v1'}, 'files': {'file': ('input.csv', b'Area,Room,Age\n80,2,15\n', 'text/csv')}}
    assert browser.post('/api/predict', **params).status_code == 403
    response = browser.post('/api/predict', headers={'X-CSRF-Token': csrf}, **params)
    assert response.status_code == 200 and 'prediction' in response.text
    assert browser.get('/api/auth/tokens').status_code == 200
    assert browser.delete('/api/auth/session', headers={'X-EdgeML-Login': '1'}).status_code == 403
    assert browser.delete('/api/auth/session', headers={'X-EdgeML-Login': '1', 'X-CSRF-Token': csrf}).status_code == 200
    browser.cookies.set('edgeml_session', raw)
    assert browser.get('/api/models').status_code == 401


def test_api_token_remains_independent_and_never_becomes_web_password(browser):
    assert login(browser, password='integration-only-token').status_code == 401
    assert browser.get('/api/models', headers={'Authorization': 'Bearer integration-only-token'}).status_code == 200
    assert browser.post('/api/predict', headers={'Authorization': 'Bearer integration-only-token'}).status_code == 422
    login(browser)
    assert browser.get('/api/models', headers={'Authorization': 'Bearer invalid'}).status_code == 401


def test_login_csrf_and_shared_throttle(browser):
    assert login(browser, Origin='https://untrusted.example').status_code == 403
    assert browser.post('/api/auth/session', json={'username': 'admin', 'password': 'a-separate-web-password'}).status_code == 403
    for _ in range(5):
        assert login(browser, password='incorrect').status_code == 401
    other_process = TestClient(create_app())
    assert login(other_process).status_code == 429


def test_sessions_survive_app_recreation_but_expire_and_rotate(browser, monkeypatch):
    first = login(browser)
    raw = browser.cookies.get('edgeml_session')
    other = TestClient(create_app())
    other.cookies.set('edgeml_session', raw)
    assert other.get('/api/models').status_code == 200
    second = login(browser)
    assert second.json()['csrf_token'] != first.json()['csrf_token']
    assert other.get('/api/models').status_code == 401
    token = browser.cookies.get('edgeml_session')
    with sqlite3.connect(get_settings().api_tokens_database) as db:
        row = db.execute('SELECT digest FROM web_sessions').fetchone()
        assert row[0] == digest(token) and row[0] != token
        db.execute('UPDATE web_sessions SET expires = 0')
    assert browser.get('/api/models').status_code == 401
    login(browser)
    monkeypatch.setenv('EDGEML_WEB_PASSWORD', 'a-different-admin-password')
    get_settings.cache_clear()
    assert browser.get('/api/models').status_code == 401


def test_password_alone_protects_api_and_secure_cookie(monkeypatch):
    monkeypatch.setenv('EDGEML_WEB_PASSWORD', 'a-separate-web-password')
    monkeypatch.setenv('EDGEML_WEB_COOKIE_SECURE', 'true')
    get_settings.cache_clear()
    browser = TestClient(create_app(), base_url='https://testserver')
    assert browser.get('/api/models').status_code == 401
    assert 'Secure' in login(browser).headers['set-cookie']
    assert browser.get('/api/models').status_code == 200


def test_unconfigured_login_and_anonymous_development():
    browser = TestClient(create_app())
    state = browser.get('/api/auth/session')
    assert state.headers['cache-control'] == 'no-store'
    assert state.json()['required'] is False
    assert login(browser).status_code == 503
    assert browser.get('/api/models').status_code == 200
