"""Ограничитель попыток (верификация заказа и др.)."""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AttemptLimitResult:
    """Результат проверки лимита попыток."""

    allowed: bool
    attempts: int
    max_attempts: int
    blocked_seconds_remaining: int = 0

    @property
    def is_blocked(self) -> bool:
        return self.blocked_seconds_remaining > 0


class AttemptLimiter:
    """Счётчик попыток в окне времени с последующей блокировкой.

    По умолчанию (ТЗ): 5 попыток / 15 минут → блок на 30 минут.
    """

    def __init__(
        self,
        redis: Redis,
        *,
        max_attempts: int = 5,
        window_seconds: int = 900,
        block_seconds: int = 1800,
        key_prefix: str = "limits",
    ) -> None:
        self._redis = redis
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._block_seconds = block_seconds
        self._key_prefix = key_prefix

    def _attempts_key(self, scope: str, subject: str) -> str:
        return f"{self._key_prefix}:attempts:{scope}:{subject}"

    def _block_key(self, scope: str, subject: str) -> str:
        return f"{self._key_prefix}:block:{scope}:{subject}"

    async def check(self, scope: str, subject: str) -> AttemptLimitResult:
        """Проверяет, разрешена ли новая попытка (без инкремента)."""
        block_ttl = await self._redis.ttl(self._block_key(scope, subject))
        if block_ttl and block_ttl > 0:
            return AttemptLimitResult(
                allowed=False,
                attempts=self._max_attempts,
                max_attempts=self._max_attempts,
                blocked_seconds_remaining=block_ttl,
            )

        raw = await self._redis.get(self._attempts_key(scope, subject))
        attempts = int(raw) if raw is not None else 0
        return AttemptLimitResult(
            allowed=attempts < self._max_attempts,
            attempts=attempts,
            max_attempts=self._max_attempts,
        )

    async def hit(self, scope: str, subject: str) -> AttemptLimitResult:
        """Регистрирует неудачную попытку и при необходимости блокирует."""
        block_ttl = await self._redis.ttl(self._block_key(scope, subject))
        if block_ttl and block_ttl > 0:
            return AttemptLimitResult(
                allowed=False,
                attempts=self._max_attempts,
                max_attempts=self._max_attempts,
                blocked_seconds_remaining=block_ttl,
            )

        key = self._attempts_key(scope, subject)
        attempts = await self._redis.incr(key)
        if attempts == 1:
            await self._redis.expire(key, self._window_seconds)

        if attempts >= self._max_attempts:
            await self._redis.set(
                self._block_key(scope, subject),
                "1",
                ex=self._block_seconds,
            )
            await self._redis.delete(key)
            logger.info(
                "attempt_limit_blocked",
                scope=scope,
                subject=subject,
                block_seconds=self._block_seconds,
            )
            return AttemptLimitResult(
                allowed=False,
                attempts=attempts,
                max_attempts=self._max_attempts,
                blocked_seconds_remaining=self._block_seconds,
            )

        return AttemptLimitResult(
            allowed=True,
            attempts=int(attempts),
            max_attempts=self._max_attempts,
        )

    async def reset(self, scope: str, subject: str) -> None:
        """Сбрасывает счётчик и блок (например после успешной верификации)."""
        await self._redis.delete(
            self._attempts_key(scope, subject),
            self._block_key(scope, subject),
        )
