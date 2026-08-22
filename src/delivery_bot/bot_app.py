"""Запуск Telegram-бота (aiogram) и sidecar health-сервера."""

from __future__ import annotations

import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from delivery_bot.config import get_settings
from delivery_bot.dialog import AttemptLimiter, DialogManager, RedisSessionStore
from delivery_bot.handlers import setup_routers
from delivery_bot.health import start_health_server
from delivery_bot.logging_setup import get_logger, setup_logging
from delivery_bot.middleware import DialogSessionMiddleware
from delivery_bot.redis_client import create_redis, ping_redis


async def _run() -> None:
    settings = get_settings()
    setup_logging(settings)
    logger = get_logger(__name__)

    if not settings.telegram_bot_token or settings.telegram_bot_token.startswith(
        "replace_me"
    ):
        logger.error(
            "telegram_token_missing",
            hint="Задайте TELEGRAM_BOT_TOKEN в .env",
        )
        sys.exit(1)

    redis = create_redis(settings)
    if not await ping_redis(redis):
        logger.error("redis_unavailable", redis_url=settings.redis_url)
        await redis.aclose()
        sys.exit(1)

    session_store = RedisSessionStore(
        redis,
        session_ttl_seconds=settings.session_ttl_seconds,
        consent_ttl_seconds=settings.consent_ttl_seconds,
    )
    attempt_limiter = AttemptLimiter(
        redis,
        max_attempts=settings.verify_max_attempts,
        window_seconds=settings.verify_attempt_window_seconds,
        block_seconds=settings.verify_block_seconds,
    )
    dialog_manager = DialogManager()

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp["dialog_manager"] = dialog_manager
    dp["attempt_limiter"] = attempt_limiter
    dp["redis"] = redis
    dp.update.middleware(DialogSessionMiddleware(session_store))
    dp.include_router(setup_routers())

    health_runner = await start_health_server(
        host=settings.health_host,
        port=settings.health_port,
        redis=redis,
    )

    logger.info(
        "bot_starting",
        env=settings.app_env,
        health_port=settings.health_port,
        session_ttl=settings.session_ttl_seconds,
    )

    try:
        await dp.start_polling(bot)
    finally:
        await health_runner.cleanup()
        await bot.session.close()
        await redis.aclose()
        logger.info("bot_stopped")


def run_bot() -> None:
    """Синхронная обёртка для ``python -m delivery_bot``."""
    asyncio.run(_run())
