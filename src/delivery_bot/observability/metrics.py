"""Prometheus-метрики (API + bot)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from delivery_bot.config import get_settings

_HAS_PROM: bool
_prom_generate_latest: Callable[..., bytes] | None
try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram
    from prometheus_client import generate_latest as _prom_generate_latest_impl

    _HAS_PROM = True
    _prom_generate_latest = _prom_generate_latest_impl
except ImportError:  # pragma: no cover - fallback без зависимости
    _HAS_PROM = False
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    _prom_generate_latest = None

    class Counter:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def labels(self, **kwargs: Any) -> Any:
            return self

        def inc(self, amount: float = 1) -> None:
            pass

    class Histogram:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def labels(self, **kwargs: Any) -> Any:
            return self

        def observe(self, amount: float) -> None:
            pass


HTTP_REQUESTS = Counter(
    "delivery_http_requests_total",
    "HTTP requests to API",
    ["method", "path", "status"],
)
HTTP_LATENCY = Histogram(
    "delivery_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
BOT_INTENTS = Counter(
    "delivery_bot_intents_total",
    "Recognized bot intents",
    ["intent"],
)
VERIFY_ATTEMPTS = Counter(
    "delivery_verify_attempts_total",
    "Order verification attempts",
    ["result"],
)
ESCALATIONS = Counter(
    "delivery_escalations_total",
    "CRM escalation tickets created",
    ["reason"],
)


def metrics_enabled() -> bool:
    return get_settings().metrics_enabled


def setup_metrics() -> None:
    """Заглушка инициализации (метрики регистрируются при import)."""
    if not metrics_enabled():
        return


def render_metrics() -> tuple[bytes, str]:
    if not metrics_enabled() or not _HAS_PROM or _prom_generate_latest is None:
        return b"", CONTENT_TYPE_LATEST
    return _prom_generate_latest(), CONTENT_TYPE_LATEST


def inc_bot_intent(intent: str) -> None:
    if metrics_enabled():
        BOT_INTENTS.labels(intent=intent).inc()


def inc_verify_attempt(*, success: bool) -> None:
    if metrics_enabled():
        VERIFY_ATTEMPTS.labels(result="success" if success else "failure").inc()


def inc_escalation(reason: str) -> None:
    if metrics_enabled():
        ESCALATIONS.labels(reason=reason.split(":", 1)[0][:32]).inc()
