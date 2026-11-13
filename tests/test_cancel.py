"""Тесты отмены заказа и возврата."""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fakeredis.aioredis import FakeRedis

from delivery_bot.dialog.session import DialogSession
from delivery_bot.dialog.states import DialogState
from delivery_bot.integrations.oms.cache import OrderStatusCache
from delivery_bot.integrations.oms.cancel_schemas import CANCEL_REASONS, CancelResponse
from delivery_bot.integrations.oms.client import OmsClient
from delivery_bot.integrations.oms.schemas import OrderDTO, OrderItemDTO
from delivery_bot.integrations.payments.mock import MockPaymentGateway
from delivery_bot.services.order_cancel import OrderCancelService
from delivery_bot.services.order_policy import can_cancel


def test_cancel_reasons_catalog() -> None:
    codes = {c for c, _ in CANCEL_REASONS}
    assert "changed_mind" in codes
    assert "other" in codes
    assert len(CANCEL_REASONS) >= 5


def test_can_cancel_policy() -> None:
    assert can_cancel("paid") is True
    assert can_cancel("assembling") is True
    assert can_cancel("ready") is True
    assert can_cancel("handed_to_courier") is False
    assert can_cancel("delivering") is False


@pytest.mark.asyncio
async def test_refund_idempotent() -> None:
    redis = FakeRedis(decode_responses=True)
    pay = MockPaymentGateway(redis)
    first = await pay.refund(
        amount=Decimal("100.00"),
        order_id="ORD-1002",
        idempotency_key="idem-1",
    )
    second = await pay.refund(
        amount=Decimal("100.00"),
        order_id="ORD-1002",
        idempotency_key="idem-1",
    )
    assert first.ok and second.ok
    assert first.payment_id == second.payment_id


def _multi_item_order() -> OrderDTO:
    return OrderDTO(
        id="ORD-1006",
        status="paid",
        address="Москва",
        delivery_slot="сегодня 19:00–21:00",
        eta_minutes=80,
        total_amount=Decimal("1540.00"),
        phone_last4="4567",
        items=[
            OrderItemDTO(
                id=1,
                name="Пицца Пепперони",
                quantity=1,
                price=Decimal("790.00"),
            ),
            OrderItemDTO(
                id=2,
                name="Салат Греческий",
                quantity=1,
                price=Decimal("450.00"),
            ),
            OrderItemDTO(
                id=3,
                name="Лимонад 0.5л",
                quantity=2,
                price=Decimal("150.00"),
            ),
        ],
    )


@pytest.mark.asyncio
async def test_cancel_full_flow() -> None:
    redis = FakeRedis(decode_responses=True)
    order = _multi_item_order()
    cancelled = order.model_copy(update={"status": "cancelled"})
    oms = AsyncMock(spec=OmsClient)
    oms.cancel_order.return_value = CancelResponse(
        ok=True,
        message="Заказ ORD-1006 отменён.",
        refund_id="rfnd_test",
        refund_amount=Decimal("1540.00"),
        order=cancelled,
    )

    cache = OrderStatusCache(redis, ttl_seconds=60)
    service = OrderCancelService(oms, cache)
    await cache.set(order)
    session = DialogSession(
        channel="telegram",
        user_id="42",
        consent_accepted=True,
        state=DialogState.MAIN_MENU,
        context={"verified_order_id": "ORD-1006", "phone_last4": "4567"},
    )

    start = await service.start(session)
    assert session.state == DialogState.CANCEL_MENU
    assert "ORD-1006" in start.text

    await service.handle_callback(session, "cancel:full")
    assert session.state == DialogState.CANCEL_AWAITING_REASON

    await service.handle_callback(session, "cancel:reason:changed_mind")
    assert session.state == DialogState.CANCEL_AWAITING_COMMENT

    await service.handle_callback(session, "cancel:comment_skip")
    assert session.state == DialogState.CANCEL_CONFIRM

    done = await service.handle_callback(session, "cancel:confirm")
    assert "отмен" in done.text.lower()
    oms.cancel_order.assert_awaited_once()
    assert session.context.get("verified_order_id") is None


@pytest.mark.asyncio
async def test_cancel_partial_flow() -> None:
    redis = FakeRedis(decode_responses=True)
    order = _multi_item_order()
    remaining = order.model_copy(
        update={
            "total_amount": Decimal("1090.00"),
            "items": [order.items[0], order.items[2]],
        }
    )
    oms = AsyncMock(spec=OmsClient)
    oms.partial_cancel.return_value = CancelResponse(
        ok=True,
        message="Позиции удалены.",
        refund_id="rfnd_part",
        refund_amount=Decimal("450.00"),
        order=remaining,
    )

    cache = OrderStatusCache(redis, ttl_seconds=60)
    service = OrderCancelService(oms, cache)
    await cache.set(order)
    session = DialogSession(
        channel="telegram",
        user_id="42",
        consent_accepted=True,
        context={"verified_order_id": "ORD-1006", "phone_last4": "4567"},
    )

    await service.start(session)
    await service.handle_callback(session, "cancel:partial")
    assert session.state == DialogState.CANCEL_SELECT_ITEMS

    await service.handle_callback(session, "cancel:item:2")
    assert session.context.get("cancel_item_ids") == [2]

    await service.handle_callback(session, "cancel:items_done")
    await service.handle_callback(session, "cancel:reason:wrong_address")
    await service.handle_input(session, "Не нужна салат")
    assert session.state == DialogState.CANCEL_CONFIRM

    done = await service.handle_callback(session, "cancel:confirm")
    assert "удален" in done.text.lower() or "позиц" in done.text.lower()
    oms.partial_cancel.assert_awaited_once()
    call_kwargs = oms.partial_cancel.await_args
    assert call_kwargs.kwargs["item_ids"] == [2]


@pytest.mark.asyncio
async def test_cancel_blocked_when_delivering() -> None:
    redis = FakeRedis(decode_responses=True)
    order = OrderDTO(
        id="ORD-1001",
        status="delivering",
        address="Москва",
        total_amount=Decimal("100"),
        phone_last4="4567",
        items=[],
    )
    cache = OrderStatusCache(redis, ttl_seconds=60)
    service = OrderCancelService(AsyncMock(spec=OmsClient), cache)
    await cache.set(order)
    session = DialogSession(
        channel="telegram",
        user_id="1",
        consent_accepted=True,
        context={"verified_order_id": "ORD-1001"},
    )
    resp = await service.start(session)
    assert "нельзя отменить" in resp.text.lower()
    assert session.state == DialogState.MAIN_MENU
