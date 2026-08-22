"""Базовый контракт канала связи с клиентом."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class OutboundMessage:
    """Унифицированное исходящее сообщение для любого канала.

    Attributes:
        chat_id: Идентификатор чата/пользователя в канале.
        text: Текст сообщения.
        buttons: Опциональные кнопки быстрого ответа (label, payload).
        meta: Произвольные метаданные (WebApp URL, parse_mode и т.п.).
    """

    chat_id: str
    text: str
    buttons: list[tuple[str, str]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


class ChannelAdapter(ABC):
    """Абстрактный адаптер канала (Telegram, Viber, WhatsApp, Web).

    На MVP рабочим является только Telegram; остальные — заглушки
    с тем же интерфейсом для будущих итераций.
    """

    channel_name: str

    @abstractmethod
    async def send_message(self, message: OutboundMessage) -> None:
        """Отправляет сообщение в канал."""

    @abstractmethod
    async def is_ready(self) -> bool:
        """Проверяет готовность канала к работе."""
