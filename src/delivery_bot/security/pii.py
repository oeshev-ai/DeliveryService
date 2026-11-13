"""Маскирование персональных данных в логах и ответах."""

from __future__ import annotations

import re
from typing import Any, cast
from urllib.parse import urlparse, urlunparse

_PHONE_RE = re.compile(r"(\+?\d[\d\s\-()]{8,}\d)")
_LAST4_FIELD_RE = re.compile(r"^(\d{4})$")
_TOKEN_LIKE_RE = re.compile(r"(?i)(token|api_key|password|secret|authorization)")
_SENSITIVE_KEYS = frozenset(
    {
        "phone",
        "phone_last4",
        "last4",
        "courier_phone",
        "telegram_bot_token",
        "api_key",
        "password",
        "token",
        "authorization",
        "redis_url",
        "database_url",
    }
)


def mask_phone(value: str) -> str:
    """Маскирует номер телефона, оставляя последние 4 цифры."""
    digits = re.sub(r"\D", "", value)
    if len(digits) < 4:
        return "***"
    return f"***{digits[-4:]}"


def mask_last4(value: str) -> str:
    """Маскирует last4 для логов (не для UI верификации)."""
    if _LAST4_FIELD_RE.match(value):
        return "****"
    return mask_phone(value)


def mask_token(value: str, *, visible: int = 4) -> str:
    """Маскирует секреты и токены."""
    if len(value) <= visible:
        return "***"
    return f"{value[:visible]}…"


def mask_redis_url(url: str) -> str:
    """Убирает пароль из Redis/DB URL."""
    parsed = urlparse(url)
    if parsed.password:
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        netloc = f"{parsed.username or ''}:{'***'}@{host}" if parsed.username else host
        return urlunparse(parsed._replace(netloc=netloc))
    return url


def mask_pii_in_mapping(data: Any) -> Any:
    """Рекурсивно маскирует известные PII-поля в dict/list/str."""
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            key_lower = str(key).lower()
            if key_lower in _SENSITIVE_KEYS:
                out[key] = _mask_by_key(key_lower, str(value))
            else:
                out[key] = mask_pii_in_mapping(value)
        return out
    if isinstance(data, list):
        return [mask_pii_in_mapping(item) for item in data]
    if isinstance(data, str):
        masked = _PHONE_RE.sub(lambda m: mask_phone(m.group(1)), data)
        return masked
    return data


def _mask_by_key(key: str, value: str) -> str:
    if key in {"phone", "courier_phone"}:
        return mask_phone(value)
    if key in {"phone_last4", "last4"}:
        return mask_last4(value)
    if key in {"redis_url", "database_url"}:
        return mask_redis_url(value)
    if key in {"telegram_bot_token", "api_key", "token", "password", "authorization"}:
        return mask_token(value)
    return mask_token(value)


def mask_pii_processor(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Structlog processor: маскирует PII в полях события."""
    return cast(dict[str, Any], mask_pii_in_mapping(event_dict))
