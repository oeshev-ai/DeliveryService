"""Валидация Telegram WebApp ``initData``."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


class TelegramInitDataError(ValueError):
    """initData отсутствует, просрочен или подпись неверна."""


@dataclass(frozen=True, slots=True)
class TelegramWebAppUser:
    """Пользователь из initData."""

    id: int
    first_name: str | None = None
    username: str | None = None


def validate_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int = 86_400,
) -> TelegramWebAppUser:
    """Проверяет HMAC-подпись initData и возвращает пользователя.

    См. https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data or not bot_token:
        raise TelegramInitDataError("initData or bot token is empty")

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise TelegramInitDataError("hash is missing")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    calculated = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(calculated, received_hash):
        raise TelegramInitDataError("invalid hash")

    auth_date_raw = parsed.get("auth_date")
    if not auth_date_raw:
        raise TelegramInitDataError("auth_date is missing")
    try:
        auth_date = int(auth_date_raw)
    except ValueError as exc:
        raise TelegramInitDataError("auth_date is invalid") from exc

    if max_age_seconds > 0 and time.time() - auth_date > max_age_seconds:
        raise TelegramInitDataError("initData expired")

    user_raw = parsed.get("user")
    if not user_raw:
        raise TelegramInitDataError("user is missing")
    try:
        user_data = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise TelegramInitDataError("user json is invalid") from exc

    user_id = user_data.get("id")
    if user_id is None:
        raise TelegramInitDataError("user.id is missing")

    return TelegramWebAppUser(
        id=int(user_id),
        first_name=user_data.get("first_name"),
        username=user_data.get("username"),
    )
