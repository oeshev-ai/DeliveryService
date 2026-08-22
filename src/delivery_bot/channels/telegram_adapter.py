"""Адаптер Telegram на базе aiogram Bot API."""

from __future__ import annotations

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from delivery_bot.channels.base import ChannelAdapter, OutboundMessage
from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)


class TelegramChannelAdapter(ChannelAdapter):
    """Отправка сообщений через aiogram ``Bot``."""

    channel_name = "telegram"

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_message(self, message: OutboundMessage) -> None:
        """Отправляет текст и опциональную inline-клавиатуру."""
        reply_markup = None
        if message.buttons:
            reply_markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=label, callback_data=payload)]
                    for label, payload in message.buttons
                ]
            )

        await self._bot.send_message(
            chat_id=int(message.chat_id),
            text=message.text,
            reply_markup=reply_markup,
            parse_mode=message.meta.get("parse_mode"),
        )
        logger.info(
            "telegram_message_sent",
            chat_id=message.chat_id,
            has_buttons=bool(message.buttons),
        )

    async def is_ready(self) -> bool:
        """Проверяет доступность Bot API через ``get_me``."""
        try:
            me = await self._bot.get_me()
            return me is not None
        except Exception:
            logger.exception("telegram_ready_check_failed")
            return False
