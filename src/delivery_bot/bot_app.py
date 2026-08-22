"""Запуск Telegram-бота (aiogram) и sidecar health-сервера."""

from __future__ import annotations

import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from delivery_bot.config import get_settings
from delivery_bot.handlers import setup_routers
from delivery_bot.health import start_health_server
from delivery_bot.logging_setup import get_logger, setup_logging


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

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(setup_routers())

    health_runner = await start_health_server(
        host=settings.health_host,
        port=settings.health_port,
    )

    logger.info(
        "bot_starting",
        env=settings.app_env,
        health_port=settings.health_port,
    )

    try:
        await dp.start_polling(bot)
    finally:
        await health_runner.cleanup()
        await bot.session.close()
        logger.info("bot_stopped")


def run_bot() -> None:
    """Синхронная обёртка для ``python -m delivery_bot``."""
    asyncio.run(_run())
