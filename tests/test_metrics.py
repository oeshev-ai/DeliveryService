"""Тесты метрик и middleware."""

from delivery_bot.api.middleware import normalize_path
from delivery_bot.observability.metrics import (
    inc_bot_intent,
    inc_verify_attempt,
    render_metrics,
)


def test_normalize_path() -> None:
    assert normalize_path("/oms/v1/orders/ORD-1004") == "/oms/v1/orders/{id}"
    assert normalize_path("/admin/v1/tickets/2/reply") == "/admin/v1/tickets/{id}/reply"


def test_metrics_render() -> None:
    inc_bot_intent("status")
    inc_verify_attempt(success=True)
    body, content_type = render_metrics()
    assert b"delivery_bot_intents_total" in body
    assert b"delivery_verify_attempts_total" in body
    assert "text/plain" in content_type
