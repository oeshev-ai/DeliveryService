"""Общие зависимости авторизации API."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from delivery_bot.config import Settings, get_settings


async def require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    """Проверяет ``X-API-Key`` в constant-time сравнении байтов UTF-8.

    ``compare_digest`` на ``str`` принимает только ASCII и иначе бросает
    ``TypeError``. Байты сравниваются для любого ключа.
    """
    if x_api_key is None or not secrets.compare_digest(
        x_api_key.encode("utf-8"),
        settings.api_key.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
