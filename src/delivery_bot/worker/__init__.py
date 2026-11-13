"""ARQ worker — отзывы, напоминания, фоновые задачи."""

from __future__ import annotations

import time

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from arq import cron
from arq.connections import RedisSettings
from redis.asyncio import Redis
from sqlalchemy import select

from delivery_bot.config import Settings, get_settings
from delivery_bot.db.migrate import apply_schema_patches
from delivery_bot.db.models import ReviewModel
from delivery_bot.db.session import (
    create_engine,
    create_session_factory,
    init_db,
    session_scope,
)
from delivery_bot.dialog import texts
from delivery_bot.integrations.crm.repository import CrmRepository
from delivery_bot.logging_setup import get_logger, setup_logging

logger = get_logger(__name__)


async def startup(ctx: dict) -> None:
    settings = get_settings()
    setup_logging(settings)
    ctx["settings"] = settings
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    ctx["redis"] = redis
    engine = create_engine(settings)
    await init_db(engine)
    await apply_schema_patches(engine)
    ctx["engine"] = engine
    ctx["session_factory"] = create_session_factory(engine)
    logger.info("worker_started", env=settings.app_env)


async def shutdown(ctx: dict) -> None:
    redis: Redis | None = ctx.get("redis")
    if redis is not None:
        await redis.aclose()
    engine = ctx.get("engine")
    if engine is not None:
        await engine.dispose()
    logger.info("worker_stopped")


async def heartbeat(ctx: dict) -> None:
    logger.debug("worker_heartbeat")


async def process_review_reminders(ctx: dict) -> None:
    """Отправляет отложенные напоминания об отзыве."""
    settings: Settings = ctx["settings"]
    redis: Redis = ctx["redis"]
    if not settings.telegram_bot_token or settings.telegram_bot_token.startswith("replace_me"):
        logger.warning("review_reminder_skipped", reason="no_bot_token")
        return

    now = time.time()
    due = await redis.zrangebyscore("review:reminder:queue", 0, now)
    if not due:
        return

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    factory = ctx["session_factory"]

    for payload in due:
        try:
            channel, user_id, order_id = payload.split(":", 2)
        except ValueError:
            await redis.zrem("review:reminder:queue", payload)
            continue

        async with session_scope(factory) as session:
            existing = await session.scalar(
                select(ReviewModel).where(
                    ReviewModel.order_id == order_id.upper(),
                    ReviewModel.user_id == user_id,
                    ReviewModel.rating.is_not(None),
                )
            )
        if existing is not None:
            await redis.zrem("review:reminder:queue", payload)
            await redis.delete(f"review:reminder:scheduled:{order_id}:{user_id}")
            continue

        if channel != "telegram":
            await redis.zrem("review:reminder:queue", payload)
            continue

        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⭐ Оставить отзыв",
                        callback_data="review:start",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Пропустить",
                        callback_data="review:skip",
                    )
                ],
            ]
        )
        try:
            await bot.send_message(
                int(user_id),
                f"Напоминание: как вам заказ <b>{order_id}</b>? " "Оцените доставку от 1 до 5 ⭐",
                reply_markup=markup,
            )
            logger.info(
                "review_reminder_sent",
                user_id=user_id,
                order_id=order_id,
            )
        except Exception as exc:
            logger.warning(
                "review_reminder_failed",
                user_id=user_id,
                order_id=order_id,
                error=str(exc),
            )
        finally:
            await redis.zrem("review:reminder:queue", payload)

    await bot.session.close()


async def process_operator_replies(ctx: dict) -> None:
    """Доставляет ответы оператора из CRM в Telegram."""
    settings: Settings = ctx["settings"]
    if not settings.telegram_bot_token or settings.telegram_bot_token.startswith("replace_me"):
        logger.warning("operator_reply_skipped", reason="no_bot_token")
        return

    factory = ctx["session_factory"]
    async with session_scope(factory) as session:
        pending = await CrmRepository(session).list_undelivered_operator_messages(limit=50)

    if not pending:
        return

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    for msg, ticket in pending:
        if ticket.channel != "telegram":
            async with session_scope(factory) as session:
                await CrmRepository(session).mark_delivered(msg.id)
            continue

        body = f"{texts.OPERATOR_REPLY_PREFIX}{msg.body}"
        try:
            await bot.send_message(int(ticket.user_id), body)
            async with session_scope(factory) as session:
                await CrmRepository(session).mark_delivered(msg.id)
            logger.info(
                "operator_reply_sent",
                ticket_id=ticket.id,
                message_id=msg.id,
                user_id=ticket.user_id,
            )
        except Exception as exc:
            logger.warning(
                "operator_reply_failed",
                ticket_id=ticket.id,
                message_id=msg.id,
                error=str(exc),
            )

    await bot.session.close()


class WorkerSettings:
    functions = [heartbeat, process_review_reminders, process_operator_replies]
    cron_jobs = [
        cron(heartbeat, minute={0, 30}),
        cron(process_review_reminders, minute=set(range(0, 60, 5))),
        cron(process_operator_replies, minute=set(range(0, 60, 2))),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
