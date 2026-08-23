"""Тесты политики статусов заказа."""

import pytest

from delivery_bot.services.order_policy import (
    OrderStatus,
    address_change_denied_reason,
    can_cancel,
    can_change_address,
    can_change_time,
)


@pytest.mark.parametrize(
    ("status", "allowed"),
    [
        (OrderStatus.CREATED, True),
        (OrderStatus.CONFIRMED, True),
        (OrderStatus.PAID, True),
        (OrderStatus.ASSEMBLING, False),
        (OrderStatus.READY, False),
        (OrderStatus.HANDED_TO_COURIER, False),
        (OrderStatus.DELIVERING, False),
        (OrderStatus.DELIVERED, False),
        (OrderStatus.CANCELLED, False),
        ("paid", True),
        ("assembling", False),
    ],
)
def test_can_change_address(status: OrderStatus | str, allowed: bool) -> None:
    assert can_change_address(status) is allowed


@pytest.mark.parametrize(
    "status",
    [
        OrderStatus.CREATED,
        OrderStatus.PAID,
        OrderStatus.ASSEMBLING,
        OrderStatus.READY,
    ],
)
def test_can_change_time_and_cancel_until_courier(status: OrderStatus) -> None:
    assert can_change_time(status) is True
    assert can_cancel(status) is True


def test_cannot_change_time_after_handed_to_courier() -> None:
    assert can_change_time(OrderStatus.HANDED_TO_COURIER) is False
    assert can_cancel(OrderStatus.HANDED_TO_COURIER) is False


def test_address_denied_reason_mentions_assembly() -> None:
    reason = address_change_denied_reason(OrderStatus.ASSEMBLING)
    assert "сборк" in reason.lower()
    assert address_change_denied_reason(OrderStatus.PAID) == ""
