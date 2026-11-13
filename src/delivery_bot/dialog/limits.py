"""Ограничитель попыток (верификация заказа и др.)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis

from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)

# KEYS[1]=attempts, KEYS[2]=block
# ARGV[1]=max_attempts, ARGV[2]=window_sec, ARGV[3]=block_sec
_HIT_LUA = """
local ttl = redis.call('TTL', KEYS[2])
if ttl > 0 then return {0, tonumber(ARGV[1]), ttl} end
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
if n >= tonumber(ARGV[1]) then
  redis.call('SET', KEYS[2], '1', 'EX', ARGV[3])
  redis.call('DEL', KEYS[1])
  return {0, n, tonumber(ARGV[3])}
end
return {1, n, 0}
"""


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
    Авторитетное решение принимает атомарный Lua-скрипт в ``hit()``.
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
        self._hit_script = redis.register_script(_HIT_LUA)

    def _attempts_key(self, scope: str, subject: str) -> str:
        return f"{self._key_prefix}:attempts:{scope}:{subject}"

    def _block_key(self, scope: str, subject: str) -> str:
        return f"{self._key_prefix}:block:{scope}:{subject}"

    async def check(self, scope: str, subject: str) -> AttemptLimitResult:
        """Проверяет, разрешена ли новая попытка (без инкремента, advisory)."""
        block_ttl = await self._redis.ttl(self._block_key(scope, subject))
        if block_ttl and block_ttl > 0:
            return AttemptLimitResult(
                allowed=False,
                attempts=self._max_attempts,
                max_attempts=self._max_attempts,
                blocked_seconds_remaining=int(block_ttl),
            )

        raw = await self._redis.get(self._attempts_key(scope, subject))
        attempts = int(raw) if raw is not None else 0
        return AttemptLimitResult(
            allowed=attempts < self._max_attempts,
            attempts=attempts,
            max_attempts=self._max_attempts,
        )

    async def hit(self, scope: str, subject: str) -> AttemptLimitResult:
        """Регистрирует неудачную попытку атомарно (Lua) и при необходимости блокирует."""
        result: Any = await self._hit_script(
            keys=[self._attempts_key(scope, subject), self._block_key(scope, subject)],
            args=[self._max_attempts, self._window_seconds, self._block_seconds],
        )
        allowed_flag, attempts, blocked_ttl = (int(result[0]), int(result[1]), int(result[2]))
        allowed = allowed_flag == 1
        if not allowed and blocked_ttl > 0 and attempts >= self._max_attempts:
            logger.info(
                "attempt_limit_blocked",
                scope=scope,
                subject=subject,
                block_seconds=self._block_seconds,
            )
        return AttemptLimitResult(
            allowed=allowed,
            attempts=attempts,
            max_attempts=self._max_attempts,
            blocked_seconds_remaining=blocked_ttl,
        )

    async def reset(self, scope: str, subject: str) -> None:
        """Сбрасывает счётчик и блок (например после успешной верификации)."""
        await self._redis.delete(
            self._attempts_key(scope, subject),
            self._block_key(scope, subject),
        )
