"""Заглушки адаптеров каналов вне MVP (Viber, WhatsApp, Web-виджет)."""

from __future__ import annotations

from delivery_bot.channels.base import ChannelAdapter, OutboundMessage
from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)


class _StubChannelAdapter(ChannelAdapter):
    """Базовая заглушка: логирует вызов, не отправляет сообщения."""

    channel_name = "stub"

    async def send_message(self, message: OutboundMessage) -> None:
        logger.warning(
            "channel_stub_send_ignored",
            channel=self.channel_name,
            chat_id=message.chat_id,
            text_preview=message.text[:80],
        )

    async def is_ready(self) -> bool:
        return False


class ViberAdapter(_StubChannelAdapter):
    """Заглушка Viber (вне MVP)."""

    channel_name = "viber"


class WhatsAppAdapter(_StubChannelAdapter):
    """Заглушка WhatsApp (вне MVP)."""

    channel_name = "whatsapp"


class WebWidgetAdapter(_StubChannelAdapter):
    """Заглушка web-виджета сайта (вне MVP; UI — через Telegram WebApp)."""

    channel_name = "web_widget"
