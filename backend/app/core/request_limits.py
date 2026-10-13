"""Bound JSON Prediction bodies before routing, decoding, or validation."""
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings


def is_json_prediction_request(scope: Scope) -> bool:
    path = scope.get('path', '').removeprefix(scope.get('root_path', ''))
    return scope.get('method') == 'POST' and path.rstrip('/') == '/api/predict/json'


class JsonPredictionBodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http' or not is_json_prediction_request(scope):
            await self.app(scope, receive, send)
            return

        limit = get_settings().max_json_body_bytes
        lengths = [value for key, value in scope.get('headers', []) if key.lower() == b'content-length']
        if lengths:
            value = lengths[0].strip()
            try:
                if len(lengths) != 1 or not value.isdigit():
                    raise ValueError('Invalid Content-Length')
                declared_length = int(value)
            except ValueError:
                await JSONResponse({'detail': 'Invalid Content-Length header.'}, status_code=400)(scope, receive, send)
                return
            if declared_length > limit:
                await self._reject(scope, receive, send, limit)
                return

        # Bound the actual bytes as well: missing, chunked, or understated
        # Content-Length must not bypass the limit. Aggregate small chunks to
        # avoid unbounded per-message overhead; no JSON decoder has run yet.
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            if len(chunk) > limit - len(body):
                await self._reject(scope, receive, send, limit)
                return
            body.extend(chunk)
            if not message.get('more_body', False):
                break

        delivered = False

        async def replay_receive() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                payload = bytes(body)
                body.clear()
                return {'type': 'http.request', 'body': payload, 'more_body': False}
            return await receive()

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send, limit: int) -> None:
        await JSONResponse({'detail': f'JSON body exceeds the {limit}-byte limit.'}, status_code=413)(scope, receive, send)


async def prediction_request_validation_handler(request: Request, exc: RequestValidationError):
    if not is_json_prediction_request(request.scope):
        return await request_validation_exception_handler(request, exc)
    # Invalid NaN/Infinity inputs cannot be echoed in a strict JSON response;
    # nested data must not be reflected either. Keep useful location/type/text.
    errors = [{key: error[key] for key in ('type', 'loc', 'msg') if key in error}
              for error in exc.errors()]
    return JSONResponse({'detail': errors}, status_code=422)
