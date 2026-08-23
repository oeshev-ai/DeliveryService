"""Тесты маскирования PII."""

from delivery_bot.security.pii import (
    mask_last4,
    mask_phone,
    mask_pii_in_mapping,
    mask_redis_url,
    mask_token,
)


def test_mask_phone() -> None:
    assert mask_phone("+79001234567") == "***4567"
    assert mask_phone("12") == "***"


def test_mask_last4() -> None:
    assert mask_last4("4567") == "****"


def test_mask_token() -> None:
    assert mask_token("dev_api_key_change_me").startswith("dev_")


def test_mask_redis_url() -> None:
    masked = mask_redis_url("redis://:secret@redis:6379/0")
    assert "secret" not in masked
    assert "redis" in masked


def test_mask_pii_in_mapping() -> None:
    data = {
        "phone": "+79001234567",
        "phone_last4": "4567",
        "message": "call +79001234567 please",
        "nested": {"api_key": "supersecret"},
    }
    out = mask_pii_in_mapping(data)
    assert out["phone"] == "***4567"
    assert out["phone_last4"] == "****"
    assert "***4567" in out["message"]
    assert out["nested"]["api_key"].startswith("supe")
