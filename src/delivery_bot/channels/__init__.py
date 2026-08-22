"""Адаптеры каналов доставки сообщений (Telegram + заглушки)."""

from delivery_bot.channels.base import ChannelAdapter, OutboundMessage
from delivery_bot.channels.stubs import ViberAdapter, WebWidgetAdapter, WhatsAppAdapter
from delivery_bot.channels.telegram_adapter import TelegramChannelAdapter

__all__ = [
    "ChannelAdapter",
    "OutboundMessage",
    "TelegramChannelAdapter",
    "ViberAdapter",
    "WhatsAppAdapter",
    "WebWidgetAdapter",
]
