"""Модель сессии диалога и хранилище в Redis."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from redis.asyncio import Redis

from delivery_bot.dialog.states import DialogState
from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class DialogSession(BaseModel):
    """Сессия диалога пользователя в канале.

    Attributes:
        channel: Имя канала (telegram, …).
        user_id: Идентификатор пользователя в канале.
        state: Текущее состояние FSM.
        context: Произвольный контекст сценария (order_id и т.п.).
        consent_accepted: Принято ли согласие на обработку ПДн.
        last_intent: Последний распознанный intent.
        updated_at: Время последнего обновления (UTC).
    """

    channel: str
    user_id: str
    state: DialogState = DialogState.IDLE
    context: dict[str, Any] = Field(default_factory=dict)
    consent_accepted: bool = False
    last_intent: str | None = None
    updated_at: datetime = Field(default_factory=_utcnow)

    def touch(self) -> None:
        """Обновляет метку активности."""
        self.updated_at = _utcnow()


class RedisSessionStore:
    """Хранилище сессий и флага согласия в Redis.

    Ключи:
      - ``dialog:session:{channel}:{user_id}`` — сессия (скользящий TTL)
      - ``dialog:consent:{channel}:{user_id}`` — согласие ПДн (длинный TTL)
    """

    def __init__(
        self,
        redis: Redis,
        *,
        session_ttl_seconds: int = 1800,
        consent_ttl_seconds: int = 31_536_000,
    ) -> None:
        self._redis = redis
        self._session_ttl = session_ttl_seconds
        self._consent_ttl = consent_ttl_seconds

    @property
    def redis(self) -> Redis:
        """Клиент Redis, используемый хранилищем сессий."""
        return self._redis

    @staticmethod
    def _session_key(channel: str, user_id: str) -> str:
        return f"dialog:session:{channel}:{user_id}"

    @staticmethod
    def _consent_key(channel: str, user_id: str) -> str:
        return f"dialog:consent:{channel}:{user_id}"

    async def get(self, channel: str, user_id: str) -> DialogSession:
        """Загружает сессию или создаёт новую; подтягивает согласие из отдельного ключа."""
        raw = await self._redis.get(self._session_key(channel, user_id))
        consent = await self._redis.get(self._consent_key(channel, user_id))
        consent_accepted = consent == "1" or consent == b"1"

        if raw is None:
            session = DialogSession(
                channel=channel,
                user_id=user_id,
                consent_accepted=bool(consent_accepted),
                state=(DialogState.MAIN_MENU if consent_accepted else DialogState.AWAITING_CONSENT),
            )
            if consent_accepted:
                # Сессия истекла, согласие сохранено
                session.state = DialogState.SESSION_EXPIRED
            logger.debug(
                "session_created",
                channel=channel,
                user_id=user_id,
                state=session.state,
            )
            return session

        payload = json.loads(raw)
        session = DialogSession.model_validate(payload)
        session.consent_accepted = bool(consent_accepted) or session.consent_accepted
        return session

    async def save(self, session: DialogSession) -> None:
        """Сохраняет сессию и продлевает TTL."""
        session.touch()
        key = self._session_key(session.channel, session.user_id)
        await self._redis.set(
            key,
            session.model_dump_json(),
            ex=self._session_ttl,
        )
        if session.consent_accepted:
            await self._redis.set(
                self._consent_key(session.channel, session.user_id),
                "1",
                ex=self._consent_ttl,
            )
        logger.debug(
            "session_saved",
            channel=session.channel,
            user_id=session.user_id,
            state=session.state,
        )

    async def clear_session(self, channel: str, user_id: str) -> None:
        """Удаляет только сессию (согласие не трогает)."""
        await self._redis.delete(self._session_key(channel, user_id))
