"""API полной и частичной отмены заказа + возврат."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from delivery_bot.api.oms_routes import get_db_session
from delivery_bot.config import Settings, get_settings
from delivery_bot.db.models import OrderModel
from delivery_bot.integrations.oms.cancel_schemas import (
    CANCEL_REASONS,
    CancelReasonDTO,
    CancelResponse,
    FullCancelRequest,
    PartialCancelRequest,
)
from delivery_bot.integrations.oms.repository import OmsRepository, to_order_dto
from delivery_bot.integrations.payments.mock import MockPaymentGateway
from delivery_bot.services.order_policy import OrderStatus, can_cancel

router = APIRouter(prefix="/oms/v1", tags=["order-cancel"])

_REASON_LABELS = dict(CANCEL_REASONS)


async def _require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if not x_api_key or x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


async def _get_redis(request: Request) -> Redis:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="Redis is not configured")
    return cast(Redis, redis)


async def _do_full_cancel(
    *,
    order: OrderModel,
    reason_code: str,
    comment: str,
    idempotency_key: str,
    session: AsyncSession,
    redis: Redis,
) -> CancelResponse:
    if order.status == OrderStatus.CANCELLED.value:
        return CancelResponse(ok=False, message="Заказ уже отменён.")

    if not can_cancel(order.status):
        return CancelResponse(
            ok=False,
            message=(
                "Заказ уже нельзя отменить — он передан курьеру "
                "или дальше по процессу. Нажмите «Связаться с оператором»."
            ),
        )

    if reason_code not in _REASON_LABELS:
        return CancelResponse(ok=False, message="Неизвестная причина отмены.")

    refund_amount = Decimal(order.total_amount)
    payments = MockPaymentGateway(redis)
    pay = await payments.refund(
        amount=refund_amount,
        order_id=order.id,
        idempotency_key=idempotency_key,
        description=f"Полная отмена {order.id}: {reason_code}",
    )
    if not pay.ok:
        return CancelResponse(ok=False, message=pay.message)

    order.status = OrderStatus.CANCELLED.value
    order.eta_minutes = None
    await session.flush()

    reason_label = _REASON_LABELS[reason_code]
    note = (comment or "").strip()
    extra = f"\nКомментарий: {note}" if note else ""

    return CancelResponse(
        ok=True,
        message=(
            f"Заказ {order.id} отменён.\n" f"Причина: {reason_label}.{extra}\n" f"{pay.message}."
        ),
        refund_id=pay.payment_id,
        refund_amount=refund_amount,
        order=to_order_dto(order),
    )


@router.get("/cancel-reasons", response_model=list[CancelReasonDTO])
async def list_cancel_reasons(
    _: None = Depends(_require_api_key),
) -> list[CancelReasonDTO]:
    return [CancelReasonDTO(code=code, label=label) for code, label in CANCEL_REASONS]


@router.post("/orders/cancel", response_model=CancelResponse)
async def cancel_order_full(
    body: FullCancelRequest,
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(_get_redis),
) -> CancelResponse:
    """Полная отмена заказа с возвратом."""
    repo = OmsRepository(session)
    order = await repo.get_by_id(body.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return await _do_full_cancel(
        order=order,
        reason_code=body.reason_code,
        comment=body.comment,
        idempotency_key=body.idempotency_key,
        session=session,
        redis=redis,
    )


@router.post("/orders/partial-cancel", response_model=CancelResponse)
async def cancel_order_partial(
    body: PartialCancelRequest,
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(_get_redis),
) -> CancelResponse:
    """Частичная отмена позиций с пропорциональным возвратом."""
    repo = OmsRepository(session)
    order = await repo.get_by_id(body.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status == OrderStatus.CANCELLED.value:
        return CancelResponse(ok=False, message="Заказ уже отменён.")

    if not can_cancel(order.status):
        return CancelResponse(
            ok=False,
            message="Частичная отмена недоступна на текущем статусе заказа.",
        )

    if body.reason_code not in _REASON_LABELS:
        return CancelResponse(ok=False, message="Неизвестная причина отмены.")

    items_by_id = {item.id: item for item in order.items}
    to_remove = []
    for item_id in body.item_ids:
        item = items_by_id.get(item_id)
        if item is None:
            return CancelResponse(
                ok=False,
                message=f"Позиция id={item_id} не найдена в заказе.",
            )
        to_remove.append(item)

    if len(to_remove) >= len(order.items):
        return await _do_full_cancel(
            order=order,
            reason_code=body.reason_code,
            comment=body.comment,
            idempotency_key=body.idempotency_key,
            session=session,
            redis=redis,
        )

    refund_amount = sum(
        (Decimal(i.price) * i.quantity for i in to_remove),
        Decimal("0"),
    )
    payments = MockPaymentGateway(redis)
    pay = await payments.refund(
        amount=refund_amount,
        order_id=order.id,
        idempotency_key=body.idempotency_key,
        description=f"Частичная отмена {order.id}",
    )
    if not pay.ok:
        return CancelResponse(ok=False, message=pay.message)

    removed_names = [i.name for i in to_remove]
    for item in to_remove:
        await session.delete(item)

    order.total_amount = Decimal(order.total_amount) - refund_amount
    if order.total_amount < 0:
        order.total_amount = Decimal("0")
    await session.flush()
    await session.refresh(order)

    reason_label = _REASON_LABELS[body.reason_code]
    note = (body.comment or "").strip()
    extra = f"\nКомментарий: {note}" if note else ""

    return CancelResponse(
        ok=True,
        message=(
            f"Из заказа {order.id} удалены позиции: {', '.join(removed_names)}.\n"
            f"Причина: {reason_label}.{extra}\n"
            f"{pay.message}.\n"
            f"Новая сумма: {order.total_amount} ₽."
        ),
        refund_id=pay.payment_id,
        refund_amount=refund_amount,
        order=to_order_dto(order),
    )
