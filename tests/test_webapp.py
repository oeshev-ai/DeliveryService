"""Тесты Telegram WebApp: initData, bindings, URL."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from fakeredis.aioredis import FakeRedis

from delivery_bot.dialog.keyboards import _webapp_order_url
from delivery_bot.webapp.bindings import WebAppBindingStore
from delivery_bot.webapp.colors import status_color
from delivery_bot.webapp.telegram_auth import (
    TelegramInitDataError,
    validate_init_data,
)


def _make_init_data(bot_token: str, user_id: int = 42) -> str:
    user = json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":"))
    fields = {
        "auth_date": str(int(time.time())),
        "query_id": "AAE",
        "user": user,
    }
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_validate_init_data_ok() -> None:
    token = "123456:ABC-DEF"
    init_data = _make_init_data(token, user_id=7)
    user = validate_init_data(init_data, token)
    assert user.id == 7


def test_validate_init_data_bad_hash() -> None:
    token = "123456:ABC-DEF"
    init_data = _make_init_data(token) + "tamper"
    with pytest.raises(TelegramInitDataError):
        validate_init_data(init_data, token)


@pytest.mark.asyncio
async def test_binding_grant_and_access() -> None:
    redis = FakeRedis(decode_responses=True)
    store = WebAppBindingStore(redis, ttl_seconds=60)
    await store.grant("100", order_id="ORD-1001", phone_last4="4567")
    assert await store.can_access("100", "ORD-1001") is True
    assert await store.can_access("100", "ORD-9999") is False
    assert await store.can_access("200", "ORD-1001") is False
    await redis.aclose()


def test_webapp_order_url() -> None:
    assert (
        _webapp_order_url("http://localhost:8000/ui", "ORD-1001")
        == "http://localhost:8000/ui/?order_id=ORD-1001"
    )
    assert (
        _webapp_order_url("http://localhost:8000/ui", "ORD-1001", tab="map")
        == "http://localhost:8000/ui/?order_id=ORD-1001&tab=map#tab=map"
    )


def test_is_telegram_webapp_url_requires_https() -> None:
    from delivery_bot.dialog.keyboards import is_telegram_webapp_url

    assert is_telegram_webapp_url("https://example.com/ui") is True
    assert is_telegram_webapp_url("http://localhost:8000/ui") is False
    assert is_telegram_webapp_url(None) is False


def test_status_color_delivering_is_green() -> None:
    assert status_color("delivering") == "#22C55E"
    assert status_color("cancelled") == "#EF4444"
