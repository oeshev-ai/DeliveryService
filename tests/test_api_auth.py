"""Тесты constant-time проверки API key."""

from __future__ import annotations

from fastapi.testclient import TestClient

from delivery_bot.api import create_api_app
from delivery_bot.config import get_settings


def test_oms_rejects_invalid_api_key() -> None:
    """Неверный X-API-Key → 401."""
    get_settings.cache_clear()
    client = TestClient(create_api_app(enable_lifespan=False))
    resp = client.get(
        "/oms/v1/cancel-reasons",
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid API key"


def test_oms_accepts_valid_api_key() -> None:
    """Верный X-API-Key проходит проверку."""
    get_settings.cache_clear()
    settings = get_settings()
    client = TestClient(create_api_app(enable_lifespan=False))
    resp = client.get(
        "/oms/v1/cancel-reasons",
        headers={"X-API-Key": settings.api_key},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
