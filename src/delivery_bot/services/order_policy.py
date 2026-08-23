"""Бизнес-правила по статусам заказа.

Статусная модель (ТЗ):
  created → confirmed → paid → assembling → ready →
  handed_to_courier → delivering → delivered
  (+ cancelled)

Изменение адреса: только пока заказ ещё не передан в сборку
(до статуса ``assembling`` исключительно).
"""

from __future__ import annotations

from enum import StrEnum


class OrderStatus(StrEnum):
    """Статусы заказа в OMS."""

    CREATED = "created"
    CONFIRMED = "confirmed"
    PAID = "paid"
    ASSEMBLING = "assembling"
    READY = "ready"
    HANDED_TO_COURIER = "handed_to_courier"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


# Адрес можно менять только до передачи в сборку
_ADDRESS_CHANGE_ALLOWED: frozenset[OrderStatus] = frozenset(
    {
        OrderStatus.CREATED,
        OrderStatus.CONFIRMED,
        OrderStatus.PAID,
    }
)

# Время / отмена — до передачи курьеру (как в исходном ТЗ)
_PRE_COURIER: frozenset[OrderStatus] = frozenset(
    {
        OrderStatus.CREATED,
        OrderStatus.CONFIRMED,
        OrderStatus.PAID,
        OrderStatus.ASSEMBLING,
        OrderStatus.READY,
    }
)


def can_change_address(status: OrderStatus | str) -> bool:
    """True, если заказ ещё не передан в сборку."""
    return _as_status(status) in _ADDRESS_CHANGE_ALLOWED


def can_change_time(status: OrderStatus | str) -> bool:
    """True, если заказ ещё не передан курьеру."""
    return _as_status(status) in _PRE_COURIER


def can_cancel(status: OrderStatus | str) -> bool:
    """True, если полная/частичная отмена ещё допустима."""
    return _as_status(status) in _PRE_COURIER


def can_replace_items(status: OrderStatus | str) -> bool:
    """True, если замена позиций ещё допустима."""
    return _as_status(status) in _PRE_COURIER


def can_claim(status: OrderStatus | str) -> bool:
    """True, если заказ доставлен и потенциально доступен для претензии."""
    return _as_status(status) == OrderStatus.DELIVERED


def can_reorder(status: OrderStatus | str) -> bool:
    """True, если заказ можно повторить из истории."""
    return _as_status(status) in {
        OrderStatus.DELIVERED,
        OrderStatus.CANCELLED,
    }


def can_review(status: OrderStatus | str) -> bool:
    """True, если заказ доставлен и можно оставить отзыв."""
    return _as_status(status) == OrderStatus.DELIVERED


def address_change_denied_reason(status: OrderStatus | str) -> str:
    """Человекочитаемая причина отказа в смене адреса."""
    st = _as_status(status)
    if st in _ADDRESS_CHANGE_ALLOWED:
        return ""
    if st == OrderStatus.CANCELLED:
        return "Заказ уже отменён — адрес изменить нельзя."
    if st == OrderStatus.DELIVERED:
        return "Заказ уже доставлен — адрес изменить нельзя."
    if st in {
        OrderStatus.ASSEMBLING,
        OrderStatus.READY,
        OrderStatus.HANDED_TO_COURIER,
        OrderStatus.DELIVERING,
    }:
        return (
            "Заказ уже передан в сборку или дальше по процессу — "
            "изменить адрес нельзя.\n"
            "Нажмите «Связаться с оператором», если нужна помощь."
        )
    return "Сейчас изменить адрес нельзя."


def _as_status(status: OrderStatus | str) -> OrderStatus:
    if isinstance(status, OrderStatus):
        return status
    return OrderStatus(str(status).lower())
