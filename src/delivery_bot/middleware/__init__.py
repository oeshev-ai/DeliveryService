"""Middleware загрузки/сохранения диалоговой сессии."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update, User
from redis.asyncio import Redis

from delivery_bot.dialog.session import DialogSession, RedisSessionStore
from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)

CHANNEL = "telegram"
_LOCK_TTL_MS = 10_000
_LOCK_WAIT_SEC = 5.0
_LOCK_RETRY_SEC = 0.1
_CONTENTION_TEXT = "Обрабатываю ваше предыдущее сообщение, секунду…"

_RELEASE_LOCK_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


class DialogSessionMiddleware(BaseMiddleware):
    """Подгружает ``DialogSession`` в ``data`` и сохраняет после handler.

    Вешается на ``dp.update``: событие приходит как ``Update``, не как Message.
    Параллельные апдейты одного пользователя сериализуются Redis-локом.
    """

    def __init__(self, store: RedisSessionStore, redis: Redis | None = None) -> None:
        self._store = store
        self._redis = redis if redis is not None else store.redis
        self._release_script = self._redis.register_script(_RELEASE_LOCK_LUA)

    def _lock_key(self, user_id: str) -> str:
        return f"dialog:lock:{CHANNEL}:{user_id}"

    async def _acquire_lock(self, user_id: str) -> str | None:
        """SET NX PX с токеном; ждёт до 5 с. Возвращает токен или None."""
        key = self._lock_key(user_id)
        token = uuid.uuid4().hex
        deadline = asyncio.get_running_loop().time() + _LOCK_WAIT_SEC
        while True:
            acquired = await self._redis.set(key, token, nx=True, px=_LOCK_TTL_MS)
            if acquired:
                return token
            if asyncio.get_running_loop().time() >= deadline:
                return None
            await asyncio.sleep(_LOCK_RETRY_SEC)

    async def _release_lock(self, user_id: str, token: str) -> None:
        """Compare-and-del: чужой/протухший лок не удаляется."""
        await self._release_script(keys=[self._lock_key(user_id)], args=[token])

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = _extract_user_id(event, data)
        if user_id is None:
            return await handler(event, data)

        token = await self._acquire_lock(user_id)
        if token is None:
            logger.info("dialog_session_lock_contention", channel=CHANNEL, user_id=user_id)
            await _reply_contention(event)
            return None

        session = await self._store.get(CHANNEL, user_id)
        data["dialog_session"] = session
        data["session_store"] = self._store

        try:
            result = await handler(event, data)
        finally:
            current: DialogSession | None = data.get("dialog_session")
            if current is not None:
                await self._store.save(current)
            await self._release_lock(user_id, token)

        return result


async def _reply_contention(event: TelegramObject) -> None:
    """Один ответ пользователю, если лок не захвачен (событие не сохраняется).

    У callback с сообщением ``answer()`` только снимает индикатор кнопки,
    текст уходит одним сообщением в чат.
    """
    try:
        if isinstance(event, Update):
            if event.message is not None:
                await event.message.answer(_CONTENTION_TEXT)
            elif event.callback_query is not None:
                await _answer_callback_once(event.callback_query)
        elif isinstance(event, Message):
            await event.answer(_CONTENTION_TEXT)
        elif isinstance(event, CallbackQuery):
            await _answer_callback_once(event)
    except Exception as exc:  # noqa: BLE001 — UX best-effort
        logger.warning("dialog_contention_reply_failed", error=str(exc))


async def _answer_callback_once(callback: CallbackQuery) -> None:
    """Текст contention — один раз. Пустой ``answer()`` гасит загрузку кнопки."""
    if callback.message is not None:
        await callback.answer()
        await callback.message.answer(_CONTENTION_TEXT)
        return
    await callback.answer(_CONTENTION_TEXT, show_alert=False)


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
