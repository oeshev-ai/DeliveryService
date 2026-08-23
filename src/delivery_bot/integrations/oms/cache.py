"""Redis-кэш статуса заказа (TTL 60–120 с)."""

from __future__ import annotations

import json

from redis.asyncio import Redis

from delivery_bot.integrations.oms.schemas import OrderDTO


class OrderStatusCache:
    """Кэш полного DTO заказа после успешной верификации."""

    def __init__(self, redis: Redis, *, ttl_seconds: int = 90) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    @staticmethod
    def _key(order_id: str) -> str:
        return f"oms:status:{order_id.upper()}"

    async def get(self, order_id: str) -> OrderDTO | None:
        raw = await self._redis.get(self._key(order_id))
        if raw is None:
            return None
        return OrderDTO.model_validate(json.loads(raw))

    async def set(self, order: OrderDTO) -> None:
        await self._redis.set(
            self._key(order.id),
            order.model_dump_json(),
            ex=self._ttl,
        )

    async def invalidate(self, order_id: str) -> None:
        await self._redis.delete(self._key(order_id))
