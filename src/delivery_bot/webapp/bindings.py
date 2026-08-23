"""Привязка Telegram-пользователя к верифицированным заказам (для WebApp)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from redis.asyncio import Redis


@dataclass
class WebAppBinding:
    """Доступ пользователя к заказам после верификации в боте."""

    phone_last4: str
    order_ids: list[str] = field(default_factory=list)


class WebAppBindingStore:
    """Хранит в Redis, какие заказы пользователь уже подтвердил."""

    def __init__(self, redis: Redis, *, ttl_seconds: int = 86_400) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    @staticmethod
    def _key(telegram_user_id: str) -> str:
        return f"webapp:binding:{telegram_user_id}"

    async def get(self, telegram_user_id: str) -> WebAppBinding | None:
        raw = await self._redis.get(self._key(telegram_user_id))
        if raw is None:
            return None
        data = json.loads(raw)
        return WebAppBinding(
            phone_last4=str(data["phone_last4"]),
            order_ids=list(data.get("order_ids") or []),
        )

    async def grant(
        self,
        telegram_user_id: str,
        *,
        order_id: str,
        phone_last4: str,
    ) -> WebAppBinding:
        """Добавляет заказ в список доступных и обновляет last4."""
        current = await self.get(telegram_user_id)
        order_ids = list(current.order_ids) if current else []
        oid = order_id.upper()
        if oid not in order_ids:
            order_ids.insert(0, oid)
        binding = WebAppBinding(phone_last4=phone_last4, order_ids=order_ids[:20])
        await self._redis.set(
            self._key(telegram_user_id),
            json.dumps(
                {"phone_last4": binding.phone_last4, "order_ids": binding.order_ids}
            ),
            ex=self._ttl,
        )
        return binding

    async def can_access(self, telegram_user_id: str, order_id: str) -> bool:
        binding = await self.get(telegram_user_id)
        if binding is None:
            return False
        return order_id.upper() in {x.upper() for x in binding.order_ids}
