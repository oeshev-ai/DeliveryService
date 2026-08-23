"""Форматирование статуса заказа для Telegram."""

from __future__ import annotations

from delivery_bot.integrations.oms.schemas import OrderDTO, OrderSummaryDTO
from delivery_bot.services.order_policy import OrderStatus

STATUS_LABELS: dict[str, str] = {
    OrderStatus.CREATED.value: "создан",
    OrderStatus.CONFIRMED.value: "подтверждён",
    OrderStatus.PAID.value: "оплачен",
    OrderStatus.ASSEMBLING.value: "собирается",
    OrderStatus.READY.value: "готов к передаче курьеру",
    OrderStatus.HANDED_TO_COURIER.value: "передан курьеру",
    OrderStatus.DELIVERING.value: "в пути",
    OrderStatus.DELIVERED.value: "доставлен",
    OrderStatus.CANCELLED.value: "отменён",
}

# Стандарт палитры (эмодзи-индикатор в чате)
STATUS_COLORS: dict[str, str] = {
    OrderStatus.CREATED.value: "⚪️",
    OrderStatus.CONFIRMED.value: "⚪️",
    OrderStatus.PAID.value: "🔵",
    OrderStatus.ASSEMBLING.value: "🔵",
    OrderStatus.READY.value: "🟠",
    OrderStatus.HANDED_TO_COURIER.value: "🟠",
    OrderStatus.DELIVERING.value: "🟢",
    OrderStatus.DELIVERED.value: "🟢",
    OrderStatus.CANCELLED.value: "🔴",
}


def status_badge(status: str) -> str:
    color = STATUS_COLORS.get(status, "⚪️")
    label = STATUS_LABELS.get(status, status)
    return f"{color} {label}"


def format_order_status(order: OrderDTO, *, verified: bool = True) -> str:
    """Полный текст статуса после верификации."""
    lines = [
        f"Заказ <b>{order.id}</b>",
        f"Статус: {status_badge(order.status)}",
    ]
    if order.eta_minutes is not None and order.status not in {
        OrderStatus.DELIVERED.value,
        OrderStatus.CANCELLED.value,
    }:
        lines.append(f"ETA: ≈ {order.eta_minutes} мин")
    if order.delivery_slot:
        lines.append(f"Слот: {order.delivery_slot}")
    if verified:
        lines.append(f"Адрес: {order.address}")
        if order.courier_name:
            lines.append(f"Курьер: {order.courier_name}")
            if order.courier_phone:
                lines.append(f"Телефон курьера: {order.courier_phone}")
        lines.append(f"Сумма: {order.total_amount} ₽")
        if order.items:
            lines.append("Состав:")
            for item in order.items:
                flag = "" if item.available else " (нет в наличии)"
                lines.append(
                    f"• {item.name} × {item.quantity} — {item.price} ₽{flag}"
                )
    return "\n".join(lines)


def format_orders_list(orders: list[OrderSummaryDTO]) -> str:
    if not orders:
        return "Заказов не найдено."
    lines = ["Нашёлся несколько заказов — выберите номер:"]
    for o in orders:
        eta = f", ETA ≈ {o.eta_minutes} мин" if o.eta_minutes is not None else ""
        lines.append(f"• {o.id}: {status_badge(o.status)}{eta}")
    return "\n".join(lines)


def format_public_status(order_id: str, in_transit: bool) -> str:
    if in_transit:
        return (
            f"По заказу <b>{order_id}</b> вижу только: заказ <b>в пути</b>.\n"
            "Для деталей (адрес, курьер, состав) нужны последние 4 цифры телефона."
        )
    return (
        f"По заказу <b>{order_id}</b> без полной проверки могу сказать только, "
        "что он сейчас <b>не в пути</b>.\n"
        "Для деталей подтвердите последние 4 цифры телефона."
    )
