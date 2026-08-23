"""FastAPI middleware: request id, метрики, безопасность."""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

import structlog

from delivery_bot.observability.metrics import HTTP_LATENCY, HTTP_REQUESTS, metrics_enabled

_PATH_ID_RE = re.compile(
    r"(/orders/)(ORD-\d+|[^/]+)|"
    r"(/tickets/)(\d+)|"
    r"(/articles/)(\d+)"
)


def normalize_path(path: str) -> str:
    """Сводит path к шаблону без конкретных id (для метрик)."""
    normalized = _PATH_ID_RE.sub(
        lambda m: (
            f"{m.group(1)}{{id}}"
            if m.group(1)
            else f"{m.group(3)}{{id}}"
            if m.group(3)
            else f"{m.group(5)}{{id}}"
        ),
        path,
    )
    return normalized


class RequestContextMiddleware(BaseHTTPMiddleware):
    """X-Request-ID + structlog contextvars."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    """Счётчики и latency для Prometheus."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not metrics_enabled() or request.url.path == "/metrics":
            return await call_next(request)

        path = normalize_path(request.url.path)
        started = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - started
        status = str(response.status_code)
        HTTP_REQUESTS.labels(
            method=request.method,
            path=path,
            status=status,
        ).inc()
        HTTP_LATENCY.labels(method=request.method, path=path).observe(elapsed)
        return response
