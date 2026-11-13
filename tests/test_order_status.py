"""Тесты сценария статуса и форматирования."""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fakeredis.aioredis import FakeRedis

from delivery_bot.dialog.limits import AttemptLimiter
from delivery_bot.dialog.session import DialogSession
from delivery_bot.dialog.states import DialogState
from delivery_bot.integrations.oms.cache import OrderStatusCache
from delivery_bot.integrations.oms.client import OmsClient
from delivery_bot.integrations.oms.repository import phone_last4
from delivery_bot.integrations.oms.schemas import (
    OrderDTO,
    OrderPublicDTO,
    VerifyResponse,
)
from delivery_bot.services.order_status import OrderStatusService, normalize_order_id
from delivery_bot.services.status_formatter import format_order_status, format_public_status


def test_phone_last4() -> None:
    assert phone_last4("+79001234567") == "4567"
    assert phone_last4("900-123-45-67") == "4567"


def test_normalize_order_id() -> None:
    assert normalize_order_id("1001") == "ORD-1001"
    assert normalize_order_id("ord-1001") == "ORD-1001"
    assert normalize_order_id("ORD-1001") == "ORD-1001"
    assert normalize_order_id("abc") is None


def test_format_public_and_full() -> None:
    public = format_public_status("ORD-1001", True)
    assert "в пути" in public.lower()
    order = OrderDTO(
        id="ORD-1001",
        status="delivering",
        address="Москва",
        eta_minutes=25,
        total_amount=Decimal("100"),
        phone_last4="4567",
        items=[],
    )
    text = format_order_status(order)
    assert "ORD-1001" in text
    assert "Москва" in text


@pytest.mark.asyncio
async def test_status_flow_verify_success() -> None:
    redis = FakeRedis(decode_responses=True)
    oms = AsyncMock(spec=OmsClient)
    oms.get_public.return_value = OrderPublicDTO(
        id="ORD-1001", in_transit=True, status_label="в пути"
    )
    order = OrderDTO(
        id="ORD-1001",
        status="delivering",
        address="Москва, Тверская 10",
        eta_minutes=25,
        courier_name="Иван",
        courier_phone="+79001112233",
        total_amount=Decimal("1290"),
        phone_last4="4567",
        items=[],
    )
    oms.verify.return_value = VerifyResponse(ok=True, order=order)
    oms.list_by_last4.return_value = []

    service = OrderStatusService(
        oms,
        OrderStatusCache(redis, ttl_seconds=60),
        AttemptLimiter(redis, max_attempts=5, window_seconds=60, block_seconds=60),
    )
    session = DialogSession(
        channel="telegram",
        user_id="1",
        consent_accepted=True,
        state=DialogState.MAIN_MENU,
    )

    start = await service.start(session)
    assert session.state == DialogState.AWAITING_ORDER_ID
    assert "номер заказа" in start.text.lower()

    mid = await service.handle_input(session, "1001")
    assert session.state == DialogState.AWAITING_PHONE_LAST4
    assert "в пути" in mid.text.lower()

    done = await service.handle_input(session, "4567")
    assert session.context["verified_order_id"] == "ORD-1001"
    assert "Иван" in done.text
    assert "Тверская" in done.text
    await redis.aclose()


@pytest.mark.asyncio
async def test_status_flow_verify_fail_counts_attempts() -> None:
    redis = FakeRedis(decode_responses=True)
    oms = AsyncMock(spec=OmsClient)
    oms.verify.return_value = VerifyResponse(ok=False, reason="not_found_or_mismatch")

    service = OrderStatusService(
        oms,
        OrderStatusCache(redis, ttl_seconds=60),
        AttemptLimiter(redis, max_attempts=3, window_seconds=60, block_seconds=60),
    )
    session = DialogSession(
        channel="telegram",
        user_id="9",
        consent_accepted=True,
        state=DialogState.AWAITING_PHONE_LAST4,
        context={"pending_order_id": "ORD-1001"},
    )
    resp = await service.handle_input(session, "0000")
    assert "попыток" in resp.text.lower()
    await redis.aclose()


@pytest.mark.asyncio
async def test_select_sibling_reuses_verified_last4() -> None:
    """После верификации выбор другого заказа из списка не просит last4 снова."""
    redis = FakeRedis(decode_responses=True)
    oms = AsyncMock(spec=OmsClient)
    sibling = OrderDTO(
        id="ORD-1002",
        status="paid",
        address="Москва, Арбат 1",
        eta_minutes=40,
        total_amount=Decimal("500"),
        phone_last4="4567",
        items=[],
    )
    oms.verify.return_value = VerifyResponse(ok=True, order=sibling)

    service = OrderStatusService(
        oms,
        OrderStatusCache(redis, ttl_seconds=60),
        AttemptLimiter(redis, max_attempts=5, window_seconds=60, block_seconds=60),
    )
    session = DialogSession(
        channel="telegram",
        user_id="1",
        consent_accepted=True,
        state=DialogState.ORDER_STATUS,
        context={
            "verified_order_id": "ORD-1001",
            "phone_last4": "4567",
        },
    )

    resp = await service.select_order(session, "ORD-1002")
    assert session.state != DialogState.AWAITING_PHONE_LAST4
    assert session.context["verified_order_id"] == "ORD-1002"
    assert "Арбат" in resp.text
    assert "4 цифр" not in resp.text.lower()
    oms.verify.assert_awaited_once_with("ORD-1002", "4567")
    await redis.aclose()


@pytest.mark.asyncio
async def test_select_order_asks_last4_without_prior_verify() -> None:
    redis = FakeRedis(decode_responses=True)
    oms = AsyncMock(spec=OmsClient)
    service = OrderStatusService(
        oms,
        OrderStatusCache(redis, ttl_seconds=60),
        AttemptLimiter(redis, max_attempts=5, window_seconds=60, block_seconds=60),
    )
    session = DialogSession(
        channel="telegram",
        user_id="1",
        consent_accepted=True,
        state=DialogState.MAIN_MENU,
    )
    resp = await service.select_order(session, "ORD-1001")
    assert session.state == DialogState.AWAITING_PHONE_LAST4
    assert "4 цифр" in resp.text.lower()
    await redis.aclose()
