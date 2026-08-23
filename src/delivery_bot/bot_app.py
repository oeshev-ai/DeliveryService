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
from delivery_bot.integrations.crm.client import CrmClient
from delivery_bot.integrations.faq.client import FaqClient
from delivery_bot.integrations.oms.cache import OrderStatusCache
from delivery_bot.integrations.oms.client import OmsClient
from delivery_bot.integrations.oms.post_delivery_client import PostDeliveryClient
from delivery_bot.integrations.tms import MockTmsService
from delivery_bot.logging_setup import get_logger, setup_logging
from delivery_bot.middleware import DialogSessionMiddleware
from delivery_bot.observability.metrics import setup_metrics
from delivery_bot.redis_client import create_redis, ping_redis
from delivery_bot.services.claim import ClaimService
from delivery_bot.services.courier import CourierService
from delivery_bot.services.escalation import EscalationService
from delivery_bot.services.faq import FaqService
from delivery_bot.services.order_cancel import OrderCancelService
from delivery_bot.services.order_change import OrderChangeService
from delivery_bot.services.order_status import OrderStatusService
from delivery_bot.services.reorder import ReorderService
from delivery_bot.services.review import ReviewService
from delivery_bot.webapp.bindings import WebAppBindingStore


async def _run() -> None:
    settings = get_settings()
    setup_logging(settings)
    setup_metrics()
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
    oms = OmsClient(
        settings.oms_base_url,
        settings.api_key,
        timeout=settings.oms_timeout_seconds,
    )
    await oms.start()
    post_delivery = PostDeliveryClient(
        settings.oms_base_url,
        settings.api_key,
        timeout=max(5.0, settings.oms_timeout_seconds + 5.0),
    )
    await post_delivery.start()
    faq_client = FaqClient(
        settings.oms_base_url,
        settings.api_key,
        timeout=max(5.0, settings.oms_timeout_seconds + 5.0),
    )
    await faq_client.start()
    crm_client = CrmClient(
        settings.oms_base_url,
        settings.api_key,
        timeout=max(5.0, settings.oms_timeout_seconds + 5.0),
    )
    await crm_client.start()

    status_cache = OrderStatusCache(
        redis, ttl_seconds=settings.status_cache_ttl_seconds
    )
    bindings = WebAppBindingStore(
        redis, ttl_seconds=settings.webapp_binding_ttl_seconds
    )
    tms = MockTmsService()
    review_service = ReviewService(oms, post_delivery, status_cache)
    status_service = OrderStatusService(
        oms,
        status_cache,
        attempt_limiter,
        bindings=bindings,
        webapp_url=settings.telegram_webapp_url,
        review_service=review_service,
    )
    courier_service = CourierService(
        oms,
        status_cache,
        tms,
        webapp_url=settings.telegram_webapp_url,
    )
    change_service = OrderChangeService(oms, status_cache)
    cancel_service = OrderCancelService(oms, status_cache)
    faq_service = FaqService(faq_client)
    claim_service = ClaimService(oms, post_delivery, status_cache)
    reorder_service = ReorderService(oms, post_delivery, status_cache)
    escalation_service = EscalationService(crm_client)
    dialog_manager = DialogManager()

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp["dialog_manager"] = dialog_manager
    dp["status_service"] = status_service
    dp["courier_service"] = courier_service
    dp["change_service"] = change_service
    dp["cancel_service"] = cancel_service
    dp["faq_service"] = faq_service
    dp["claim_service"] = claim_service
    dp["review_service"] = review_service
    dp["reorder_service"] = reorder_service
    dp["escalation_service"] = escalation_service
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
        oms_base_url=settings.oms_base_url,
        webapp_url=settings.telegram_webapp_url,
        llm_faq=settings.llm_faq_enabled,
    )

    try:
        await dp.start_polling(bot)
    finally:
        await health_runner.cleanup()
        await bot.session.close()
        await oms.aclose()
        await post_delivery.aclose()
        await faq_client.aclose()
        await crm_client.aclose()
        await redis.aclose()
        logger.info("bot_stopped")


def run_bot() -> None:
    """Синхронная обёртка для ``python -m delivery_bot``."""
    asyncio.run(_run())
