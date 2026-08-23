"""Правила и операции претензий / отзывов / reorder."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from delivery_bot.config import Settings
from delivery_bot.db.models import OrderItemModel, OrderModel
from delivery_bot.integrations.oms.post_delivery_schemas import (
    ReorderConfirmRequest,
    ReorderConfirmResponse,
    ReorderItemDTO,
    ReorderPreviewResponse,
)
from delivery_bot.integrations.oms.repository import OmsRepository, to_order_dto
from delivery_bot.services.order_policy import OrderStatus, can_claim, can_reorder

CLAIM_WINDOW_DAYS = 14


def claim_denied_reason(
    *,
    status: str,
    delivered_at: datetime | None,
    now: datetime | None = None,
) -> str:
    if not can_claim(status):
        return "Претензию можно подать только по доставленному заказу."
    if delivered_at is None:
        return "Не удалось определить дату доставки — обратитесь к оператору."
    now = now or datetime.now(UTC)
    dt = delivered_at if delivered_at.tzinfo else delivered_at.replace(tzinfo=UTC)
    if now - dt > timedelta(days=CLAIM_WINDOW_DAYS):
        return (
            f"Срок подачи претензии истёк ({CLAIM_WINDOW_DAYS} дней после доставки)."
        )
    return ""


def can_submit_claim(
    *,
    status: str,
    delivered_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    return claim_denied_reason(
        status=status, delivered_at=delivered_at, now=now
    ) == ""


async def build_reorder_preview(
    session: AsyncSession, order_id: str
) -> ReorderPreviewResponse:
    repo = OmsRepository(session)
    order = await repo.get_by_id(order_id)
    if order is None:
        return ReorderPreviewResponse(
            ok=False,
            message="Заказ не найден.",
            source_order_id=order_id.upper(),
        )
    if not can_reorder(order.status):
        return ReorderPreviewResponse(
            ok=False,
            message="Повторить можно только доставленный или отменённый заказ.",
            source_order_id=order.id,
        )

    items: list[ReorderItemDTO] = []
    skipped: list[str] = []
    total = Decimal("0")
    for item in order.items:
        included = bool(item.available)
        dto = ReorderItemDTO(
            name=item.name,
            quantity=item.quantity,
            price=item.price,
            available=item.available,
            included=included,
        )
        items.append(dto)
        if included:
            total += Decimal(item.price) * item.quantity
        else:
            skipped.append(item.name)

    if total <= 0:
        return ReorderPreviewResponse(
            ok=False,
            message="Нет доступных позиций для повторного заказа.",
            source_order_id=order.id,
            items=items,
            skipped_items=skipped,
            address=order.address,
            delivery_slot=order.delivery_slot,
        )

    msg = "Готово к повторному заказу."
    if skipped:
        msg = (
            f"Недоступные позиции будут пропущены: {', '.join(skipped)}.\n"
            f"Новая сумма: {total} ₽."
        )
    return ReorderPreviewResponse(
        ok=True,
        message=msg,
        source_order_id=order.id,
        items=items,
        skipped_items=skipped,
        total_amount=total,
        address=order.address,
        delivery_slot=order.delivery_slot,
    )


async def confirm_reorder(
    session: AsyncSession,
    body: ReorderConfirmRequest,
    *,
    settings: Settings,
) -> ReorderConfirmResponse:
    preview = await build_reorder_preview(session, body.source_order_id)
    if not preview.ok:
        return ReorderConfirmResponse(ok=False, message=preview.message)

    repo = OmsRepository(session)
    source = await repo.get_by_id(body.source_order_id)
    if source is None:
        return ReorderConfirmResponse(ok=False, message="Исходный заказ не найден.")

    new_id = await _next_order_id(session)
    new_order = OrderModel(
        id=new_id,
        phone=source.phone,
        status=OrderStatus.CREATED.value,
        address=source.address,
        delivery_slot=source.delivery_slot,
        eta_minutes=120,
        total_amount=preview.total_amount,
        items=[
            OrderItemModel(
                name=i.name,
                quantity=i.quantity,
                price=i.price,
                available=True,
            )
            for i in preview.items
            if i.included
        ],
    )
    session.add(new_order)
    await session.flush()
    await session.refresh(new_order)

    return ReorderConfirmResponse(
        ok=True,
        message=(
            f"Создан новый заказ <b>{new_id}</b> на сумму {preview.total_amount} ₽.\n"
            f"Позиций: {len(new_order.items)}."
        ),
        order=to_order_dto(new_order),
    )


async def _next_order_id(session: AsyncSession) -> str:
    max_num = await session.scalar(
        select(func.max(OrderModel.id)).where(OrderModel.id.like("ORD-%"))
    )
    if not max_num:
        return "ORD-2001"
    try:
        num = int(str(max_num).split("-", 1)[1])
    except (IndexError, ValueError):
        num = 2000
    return f"ORD-{num + 1}"
