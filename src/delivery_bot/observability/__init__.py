"""Наблюдаемость: метрики Prometheus."""

from delivery_bot.observability.metrics import (
    inc_bot_intent,
    inc_escalation,
    inc_verify_attempt,
    metrics_enabled,
    render_metrics,
    setup_metrics,
)

__all__ = [
    "inc_bot_intent",
    "inc_escalation",
    "inc_verify_attempt",
    "metrics_enabled",
    "render_metrics",
    "setup_metrics",
]
