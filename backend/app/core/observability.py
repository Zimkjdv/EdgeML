from __future__ import annotations

import contextvars
import json
import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

from prometheus_client import Counter, Gauge, Histogram
from starlette.types import ASGIApp, Message, Receive, Scope, Send


_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("edgeml_request_id", default="-")

HTTP_REQUESTS = Counter(
    "edgeml_http_requests_total",
    "Total number of HTTP requests handled by EdgeML.",
    ("method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "edgeml_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
)
PREDICTIONS = Counter(
    "edgeml_predictions_total",
    "Prediction attempts handled by EdgeML.",
    ("outcome",),
)
TRAINING_JOBS = Counter(
    "edgeml_training_jobs_total",
    "Training jobs by final status.",
    ("status",),
)
TRAINING_ACTIVE = Gauge(
    "edgeml_training_jobs_active",
    "Number of training jobs currently running.",
)
TRAINING_DURATION = Histogram(
    "edgeml_training_job_duration_seconds",
    "Training job duration in seconds.",
)
REGISTRY_ACTIVE = Gauge(
    "edgeml_registry_active_models",
    "Number of active models currently available to Prediction.",
)


def get_request_id() -> str:
    return _request_id.get()


def new_request_id(candidate: str | None = None) -> str:
    """Use a bounded incoming ID for tracing, otherwise generate one."""

    if candidate and len(candidate) <= 128 and all(char.isalnum() or char in "-_." for char in candidate):
        return candidate
    return uuid4().hex


def record_prediction(outcome: str) -> None:
    PREDICTIONS.labels(outcome=outcome).inc()


def training_started() -> float:
    TRAINING_ACTIVE.inc()
    return time.perf_counter()


def training_finished(status: str, started_at: float) -> None:
    TRAINING_ACTIVE.dec()
    TRAINING_JOBS.labels(status=status).inc()
    TRAINING_DURATION.observe(time.perf_counter() - started_at)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }
        for key in ("event", "method", "route", "status_code", "duration_ms", "job_id", "model_id", "worker_id"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    root = logging.getLogger()
    if not any(isinstance(handler.formatter, JsonFormatter) for handler in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)
    root.setLevel(logging.INFO)


class RequestContextMiddleware:
    """Attach request IDs, request metrics, and structured access logs."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.logger = logging.getLogger("edgeml.http")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        request_id = new_request_id(headers.get(b"x-request-id", b"").decode("latin-1") or None)
        token = _request_id.set(request_id)
        started_at = time.perf_counter()
        status_code = 500
        async def send_with_context(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": response_headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        except Exception:
            self.logger.exception(
                "Unhandled request exception",
                extra={"event": "http.request.error", "method": scope.get("method"), "route": scope.get("path")},
            )
            raise
        finally:
            route = scope.get("route")
            route_name = getattr(route, "path", None) or scope.get("path", "unknown")
            duration = time.perf_counter() - started_at
            HTTP_REQUESTS.labels(scope.get("method", "UNKNOWN"), route_name, str(status_code)).inc()
            HTTP_DURATION.labels(scope.get("method", "UNKNOWN"), route_name).observe(duration)
            self.logger.info(
                "Request completed",
                extra={
                    "event": "http.request.completed",
                    "method": scope.get("method"),
                    "route": route_name,
                    "status_code": status_code,
                    "duration_ms": round(duration * 1000, 2),
                },
            )
            _request_id.reset(token)
