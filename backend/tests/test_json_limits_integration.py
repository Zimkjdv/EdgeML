"""Opt-in: use only a disposable backend/proxy with an explicitly small limit."""
import json
import os
import time

import httpx
import pytest

BACKEND = os.getenv('EDGEML_TEST_JSON_BACKEND_URL')
PROXY = os.getenv('EDGEML_TEST_JSON_PROXY_URL')
LIMIT = int(os.getenv('EDGEML_TEST_JSON_BODY_LIMIT', '1024'))
pytestmark = pytest.mark.skipif(not (BACKEND and PROXY), reason='requires isolated JSON-limit backend/Nginx stack')


@pytest.fixture(scope='module', autouse=True)
def wait_for_disposable_backend():
    if not (BACKEND and PROXY):
        return
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if httpx.get(f'{BACKEND}/health/live', timeout=1).status_code == 200:
                return
        except httpx.RequestError:
            pass
        time.sleep(0.25)
    pytest.fail('Disposable backend did not become live.')


def padded_body(size):
    body = json.dumps({'model_id': 'house-price-v1', 'data': [{'Area': 80, 'Room': 2, 'Age': 15}]}).encode()
    assert len(body) <= size
    return body + b' ' * (size - len(body))


@pytest.mark.parametrize('url', [BACKEND, PROXY])
@pytest.mark.parametrize('chunked', [False, True])
def test_exact_boundary_and_backend_rejection_via_both_paths(url, chunked):
    with httpx.Client(base_url=url, timeout=15) as client:
        def send(size):
            body = padded_body(size)
            content = iter([body[:17], body[17:]]) if chunked else body
            return client.post('/api/predict/json', content=content, headers={'Content-Type': 'application/json'})
        accepted = send(LIMIT)
        assert accepted.status_code == 200, accepted.text[:300]
        assert len(accepted.json()['records']) == 1
        rejected = send(LIMIT + 1)
        assert rejected.status_code == 413, rejected.text[:300]
        assert f'{LIMIT}-byte limit' in rejected.json()['detail']
        assert rejected.headers['x-request-id']


def test_proxy_retains_its_own_larger_body_boundary():
    # Test fixture runs Nginx with a 2k cap and Backend with a 1k cap.
    response = httpx.post(f'{PROXY}/api/predict/json', content=b'x' * (LIMIT * 3),
        headers={'Content-Type': 'application/json'}, timeout=15)
    assert response.status_code == 413


@pytest.mark.parametrize('url', [BACKEND, PROXY])
def test_invalid_scalar_contract_is_consistent_through_proxy(url):
    response = httpx.post(f'{url}/api/predict/json', json={'model_id': 'house-price-v1',
        'data': [{'Area': {'nested': 80}, 'Room': 2, 'Age': 15}]}, timeout=15)
    assert response.status_code == 422
    assert response.json()['detail'][0]['loc'][:2] == ['body', 'data']
