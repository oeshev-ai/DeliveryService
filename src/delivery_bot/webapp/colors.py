"""Цвета статусов для WebApp (стандарт палитры из ТЗ)."""

from __future__ import annotations

from delivery_bot.services.order_policy import OrderStatus
from delivery_bot.services.status_formatter import STATUS_LABELS

# grey → blue → orange → green → red
STATUS_COLOR_HEX: dict[str, str] = {
    OrderStatus.CREATED.value: "#9CA3AF",
    OrderStatus.CONFIRMED.value: "#9CA3AF",
    OrderStatus.PAID.value: "#3B82F6",
    OrderStatus.ASSEMBLING.value: "#3B82F6",
    OrderStatus.READY.value: "#F59E0B",
    OrderStatus.HANDED_TO_COURIER.value: "#F59E0B",
    OrderStatus.DELIVERING.value: "#22C55E",
    OrderStatus.DELIVERED.value: "#22C55E",
    OrderStatus.CANCELLED.value: "#EF4444",
}


def status_color(status: str) -> str:
    return STATUS_COLOR_HEX.get(status, "#9CA3AF")


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)
