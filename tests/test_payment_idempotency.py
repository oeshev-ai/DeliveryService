"""Конкурентная идемпотентность mock payments (SET NX)."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from fakeredis.aioredis import FakeRedis

from delivery_bot.integrations.payments.mock import MockPaymentGateway


@pytest.mark.asyncio
async def test_parallel_refund_same_key_same_amount() -> None:
    redis = FakeRedis(decode_responses=True)
    pay = MockPaymentGateway(redis)

    results = await asyncio.gather(
        pay.refund(amount=Decimal("100.00"), order_id="ORD-1", idempotency_key="k1"),
        pay.refund(amount=Decimal("100.00"), order_id="ORD-1", idempotency_key="k1"),
    )
    assert all(r.ok for r in results)
    assert results[0].payment_id == results[1].payment_id
    await redis.aclose()


@pytest.mark.asyncio
async def test_refund_same_key_different_amount_rejected() -> None:
    redis = FakeRedis(decode_responses=True)
    pay = MockPaymentGateway(redis)
    first = await pay.refund(amount=Decimal("100.00"), order_id="ORD-1", idempotency_key="k2")
    second = await pay.refund(amount=Decimal("50.00"), order_id="ORD-1", idempotency_key="k2")
    assert first.ok is True
    assert second.ok is False
    assert "другой суммой" in second.message
    await redis.aclose()


@pytest.mark.asyncio
async def test_refund_different_keys_different_payments() -> None:
    redis = FakeRedis(decode_responses=True)
    pay = MockPaymentGateway(redis)
    a = await pay.refund(amount=Decimal("10.00"), order_id="ORD-1", idempotency_key="a")
    b = await pay.refund(amount=Decimal("10.00"), order_id="ORD-1", idempotency_key="b")
    assert a.ok and b.ok
    assert a.payment_id != b.payment_id
    await redis.aclose()
