import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from app.api.dependencies import get_prediction_service
from app.core.config import get_settings
from app.core.request_limits import JsonPredictionBodyLimitMiddleware
from app.domain.schemas import JsonPredictionOutput, JsonPredictionRequest
from app.main import create_app


def configure_limit(monkeypatch, limit):
    monkeypatch.setenv('EDGEML_MAX_JSON_BODY_BYTES', str(limit))
    get_settings.cache_clear()


def invoke_middleware(monkeypatch, chunks, limit, headers=None, path='/api/predict/json', method='POST', root_path=''):
    configure_limit(monkeypatch, limit)
    received, downstream, sent = [], [], []
    messages = iter([{'type': 'http.request', 'body': chunk, 'more_body': i < len(chunks) - 1}
                     for i, chunk in enumerate(chunks)])
    async def receive():
        message = next(messages)
        received.append(message)
        return message
    async def send(message): sent.append(message)
    async def application(scope, receive, send):
        message = await receive()
        downstream.append(message['body'])
        await JSONResponse({'ok': True})(scope, receive, send)
    scope = dict(type='http', method=method, path=path, root_path=root_path, headers=headers or [])
    asyncio.run(JsonPredictionBodyLimitMiddleware(application)(scope, receive, send))
    status = next(m['status'] for m in sent if m['type'] == 'http.response.start')
    return status, received, downstream, sent


@pytest.mark.parametrize('headers', [[], [(b'transfer-encoding', b'chunked')], [(b'content-length', b'1')]])
def test_actual_body_limit_cannot_be_bypassed(monkeypatch, headers):
    status, received, downstream, _ = invoke_middleware(monkeypatch, [b'a' * 8, b'b' * 9, b'never read'], 16, headers)
    assert status == 413 and len(received) == 2
    assert downstream == []


def test_oversized_declared_body_is_rejected_without_reading(monkeypatch):
    status, received, downstream, _ = invoke_middleware(monkeypatch, [b'never read'], 16, [(b'content-length', b'17')])
    assert status == 413 and received == downstream == []


@pytest.mark.parametrize('headers', [[], [(b'transfer-encoding', b'chunked')], [(b'content-length', b'16')]])
def test_exact_boundary_and_small_chunks_are_replayed_intact(monkeypatch, headers):
    status, received, downstream, _ = invoke_middleware(monkeypatch, [b'x'] * 16, 16, headers)
    assert status == 200 and len(received) == 16
    assert downstream == [b'x' * 16]


@pytest.mark.parametrize('value', [b'-1', b'+12', b'abc', b'1.5', b''])
def test_invalid_length_headers_return_400_without_body_read(monkeypatch, value):
    status, received, downstream, _ = invoke_middleware(monkeypatch, [b'never read'], 16, [(b'content-length', value)])
    assert status == 400 and received == downstream == []


def test_duplicate_length_headers_are_rejected(monkeypatch):
    status, received, _, _ = invoke_middleware(monkeypatch, [b'x'], 16,
        [(b'content-length', b'1'), (b'content-length', b'1')])
    assert status == 400 and received == []


@pytest.mark.parametrize('path,root_path', [('/api/predict/json/', ''), ('/edge/api/predict/json', '/edge')])
def test_trailing_slash_and_mount_prefix_do_not_bypass_limit(monkeypatch, path, root_path):
    status, _, downstream, _ = invoke_middleware(monkeypatch, [b'x' * 17], 16, path=path, root_path=root_path)
    assert status == 413 and downstream == []


def test_other_endpoints_keep_their_existing_body_policy(monkeypatch):
    status, _, downstream, _ = invoke_middleware(monkeypatch, [b'x' * 17], 16, path='/api/datasets')
    assert status == 200 and downstream == [b'x' * 17]


def test_client_disconnect_does_not_dispatch_an_incomplete_request(monkeypatch):
    configure_limit(monkeypatch, 16)
    messages = iter([{'type': 'http.request', 'body': b'{', 'more_body': True},
                     {'type': 'http.disconnect'}])
    async def receive(): return next(messages)
    async def unexpected(*args): pytest.fail('Incomplete request must not be dispatched or answered.')
    asyncio.run(JsonPredictionBodyLimitMiddleware(unexpected)(
        {'type': 'http', 'method': 'POST', 'path': '/api/predict/json', 'headers': []}, receive, unexpected))


@pytest.mark.parametrize('field', ['data', 'records'])
@pytest.mark.parametrize('value', [[1, 2], {'nested': 'value'}, float('inf'), float('-inf'), float('nan')])
def test_nonscalar_or_nonfinite_values_return_json_safe_422_without_prediction(field, value):
    class NeverPredict:
        def predict_json(self, **kwargs): pytest.fail('invalid values reached inference')
    app = create_app()
    app.dependency_overrides[get_prediction_service] = NeverPredict
    # stdlib emits nonstandard constants here deliberately, to test rejection
    # even though most HTTP clients refuse to encode NaN/Infinity themselves.
    body = json.dumps({'model_id': 'model', field: [{'x': value}]})
    with TestClient(app) as client:
        response = client.post('/api/predict/json', content=body, headers={'Content-Type': 'application/json'})
    assert response.status_code == 422, response.text
    assert response.json()['detail'][0]['loc'][:2] == ['body', field]
    assert 'input' not in response.json()['detail'][0]


def test_scalar_types_and_large_integer_precision_are_preserved():
    record = {'中文': '甲', 'int': 2**63 + 1, 'decimal': 0.25, 'flag': True, 'missing': None}
    request = JsonPredictionRequest(model_id='model', data=[record])
    assert request.input_data == [record]
    assert type(request.input_data[0]['flag']) is bool
    assert type(request.input_data[0]['int']) is int


@pytest.mark.parametrize('number', ['1e999', '-1e999'])
def test_overflowing_standard_json_number_is_a_json_safe_validation_error(number):
    app = create_app()
    app.dependency_overrides[get_prediction_service] = lambda: None
    body = '{"model_id":"model","data":[{"x":' + number + '}]}'
    with TestClient(app) as client:
        response = client.post('/api/predict/json', content=body, headers={'Content-Type': 'application/json'})
    assert response.status_code == 422
    assert 'finite' in response.json()['detail'][0]['msg']


@pytest.mark.parametrize('chunked', [False, True])
def test_http_is_limited_before_decode_and_preserves_cors_and_request_id(monkeypatch, chunked):
    configure_limit(monkeypatch, 128)
    class NeverPredict:
        def predict_json(self, **kwargs): pytest.fail('oversized body reached inference')
    app = create_app()
    app.dependency_overrides[get_prediction_service] = NeverPredict
    async def stream():
        yield b'{' * 64  # Malformed JSON would otherwise fail during parsing.
        yield b'x' * 65
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.post('/api/predict/json', content=stream() if chunked else b'{' * 64 + b'x' * 65,
                headers={'Content-Type': 'application/json', 'Origin': 'http://localhost:5173'})
            assert response.status_code == 413 and 'JSON body exceeds' in response.json()['detail']
            assert response.headers['access-control-allow-origin'] == 'http://localhost:5173'
            assert response.headers['x-request-id']
    asyncio.run(exercise())


def test_exact_utf8_byte_limit_accepts_a_real_request(monkeypatch):
    body = json.dumps({'model_id': 'model', 'data': [{'中文': '甲'}]}, ensure_ascii=False).encode()
    configure_limit(monkeypatch, len(body))
    calls = []
    class PredictionStub:
        def predict_json(self, **kwargs):
            calls.append(kwargs)
            return JsonPredictionOutput(model_id='model', model_name='model', prediction_column='prediction', records=[])
    app = create_app()
    app.dependency_overrides[get_prediction_service] = PredictionStub
    with TestClient(app) as client:
        response = client.post('/api/predict/json', content=body, headers={'Content-Type': 'application/json'})
        assert response.status_code == 200
        response = client.post('/api/predict/json', content=body + b' ', headers={'Content-Type': 'application/json'})
        assert response.status_code == 413
    assert len(calls) == 1 and calls[0]['records'] == [{'中文': '甲'}]


def test_oversized_column_names_are_rejected(monkeypatch):
    monkeypatch.setenv('EDGEML_MAX_JSON_VALUE_CHARS', '4')
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_prediction_service] = lambda: None
    with TestClient(app) as client:
        response = client.post('/api/predict/json', json={'model_id': 'model', 'data': [{'abcde': 1}]})
    assert response.status_code == 413 and 'column names' in response.json()['detail']
