"""Middleware загрузки/сохранения диалоговой сессии."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update, User

from delivery_bot.dialog.session import DialogSession, RedisSessionStore
from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)

CHANNEL = "telegram"


class DialogSessionMiddleware(BaseMiddleware):
    """Подгружает ``DialogSession`` в ``data`` и сохраняет после handler.

    Вешается на ``dp.update``: событие приходит как ``Update``, не как Message.
    """

    def __init__(self, store: RedisSessionStore) -> None:
        self._store = store

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = _extract_user_id(event, data)
        if user_id is None:
            return await handler(event, data)

        session = await self._store.get(CHANNEL, user_id)
        data["dialog_session"] = session
        data["session_store"] = self._store

        try:
            result = await handler(event, data)
        finally:
            current: DialogSession | None = data.get("dialog_session")
            if current is not None:
                await self._store.save(current)

        return result


def _extract_user_id(event: TelegramObject, data: dict[str, Any]) -> str | None:
    """Достаёт user id из Update / Message / CallbackQuery / event_from_user."""
    from_user: User | None = data.get("event_from_user")
    if from_user is not None:
        return str(from_user.id)

    if isinstance(event, Update):
        if event.message and event.message.from_user:
            return str(event.message.from_user.id)
        if event.callback_query and event.callback_query.from_user:
            return str(event.callback_query.from_user.id)
        if event.edited_message and event.edited_message.from_user:
            return str(event.edited_message.from_user.id)
        return None

    if isinstance(event, Message) and event.from_user:
        return str(event.from_user.id)
    if isinstance(event, CallbackQuery) and event.from_user:
        return str(event.from_user.id)
    return None
