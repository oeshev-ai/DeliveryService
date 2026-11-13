"""Фабрика подключений Redis."""

from __future__ import annotations

from typing import cast

from redis.asyncio import Redis

from delivery_bot.config import Settings


def create_redis(settings: Settings) -> Redis:
    """Создаёт клиент Redis из настроек приложения."""
    return cast(
        Redis,
        Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        ),
    )


async def ping_redis(redis: Redis) -> bool:
    """Проверяет доступность Redis."""
    try:
        return bool(await redis.ping())
    except Exception:
        return False
