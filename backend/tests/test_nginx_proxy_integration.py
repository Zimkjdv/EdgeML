"""Opt-in: target an isolated disposable stack, never a developer's business stack."""
import os

import httpx
import pytest

URL = os.getenv('EDGEML_TEST_PROXY_URL')
pytestmark = pytest.mark.skipif(not URL, reason='requires isolated Nginx/backend stack')


def test_large_csv_passes_proxy_but_backend_retains_file_limit():
    with httpx.Client(base_url=URL or 'http://unused', timeout=30) as client:
        csv = b'Area,Room,Age,note\n80,2,15,' + b'a' * (1100 * 1024) + b'\n'
        result = client.post('/api/predict', data={'model_id': 'house-price-v1', 'ground_truth_column': ''},
            files={'file': ('large.csv', csv, 'text/csv')})
        assert result.status_code == 200, result.text[:300]
        assert 'prediction' in result.text.splitlines()[0]
        header = b'Area,Room,Age,note\n80,2,15,'
        boundary = header + b'a' * (5 * 1024 * 1024 - len(header) - 1) + b'\n'
        result = client.post('/api/predict', data={'model_id': 'house-price-v1', 'ground_truth_column': ''},
            files={'file': ('boundary.csv', boundary, 'text/csv')})
        assert result.status_code == 200, result.text[:300]
        large = b'Area,Room,Age,note\n80,2,15,' + b'a' * (5 * 1024 * 1024) + b'\n'
        result = client.post('/api/predict', data={'model_id': 'house-price-v1'}, files={'file': ('too-large.csv', large, 'text/csv')})
        assert result.status_code == 400
        assert 'upload size limit' in result.json()['detail']


def test_json_backend_and_proxy_limits():
    with httpx.Client(base_url=URL or 'http://unused', timeout=30) as client:
        result = client.post('/api/predict/json', json={'model_id': 'house-price-v1',
            'data': [{'Area': 80, 'Room': 2, 'Age': 15}], 'padding': 'a' * (10 * 1024 * 1024)})
        assert result.status_code == 413
        assert 'JSON body exceeds' in result.json()['detail']
        result = client.post('/api/predict/json', content=b'a' * (12 * 1024 * 1024), headers={'Content-Type': 'application/json'})
        assert result.status_code == 413
