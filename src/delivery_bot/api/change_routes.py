"""API смены адреса/времени и справочник правил доставки."""

from __future__ import annotations

from decimal import Decimal
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from delivery_bot.api.auth import require_api_key
from delivery_bot.api.oms_routes import get_db_session
from delivery_bot.integrations.oms.change_schemas import (
    AddressQuoteRequest,
    AddressQuoteResponse,
    ApplyAddressChangeRequest,
    ApplyAddressChangeResponse,
    ApplySlotChangeRequest,
    ApplySlotChangeResponse,
    DeliveryRulesDTO,
    DeliverySlotDTO,
)
from delivery_bot.integrations.oms.repository import OmsRepository, to_order_dto
from delivery_bot.integrations.payments.mock import MockPaymentGateway
from delivery_bot.services.delivery_rules import (
    find_slot,
    get_min_order_amount,
    list_slots,
    quote_address_change,
)
from delivery_bot.services.order_policy import (
    address_change_denied_reason,
    can_change_address,
    can_change_time,
)

router = APIRouter(prefix="/oms/v1", tags=["order-change"])


async def _get_redis(request: Request) -> Redis:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="Redis is not configured")
    return cast(Redis, redis)


@router.get("/delivery/rules", response_model=DeliveryRulesDTO)
async def get_delivery_rules(
    _: None = Depends(require_api_key),
) -> DeliveryRulesDTO:
    """Минимальная сумма и слоты доставки (из API)."""
    return DeliveryRulesDTO(
        min_order_amount=get_min_order_amount(),
        slots=[DeliverySlotDTO(id=s.id, label=s.label) for s in list_slots()],
    )


@router.post("/orders/quote-address", response_model=AddressQuoteResponse)
async def quote_address(
    body: AddressQuoteRequest,
    _: None = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> AddressQuoteResponse:
    """Проверка зоны и расчёт доплаты за смену адреса."""
    repo = OmsRepository(session)
    order = await repo.get_by_id(body.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    allowed = can_change_address(order.status)
    if not allowed:
        return AddressQuoteResponse(
            ok=False,
            in_zone=False,
            surcharge=Decimal("0"),
            message=address_change_denied_reason(order.status),
            normalized_address=body.address.strip(),
            can_change_address=False,
        )

    quote = quote_address_change(body.address)
    return AddressQuoteResponse(
        ok=quote.ok,
        in_zone=quote.in_zone,
        surcharge=quote.surcharge,
        message=quote.message,
        normalized_address=quote.normalized_address,
        can_change_address=True,
    )


@router.post("/orders/change-address", response_model=ApplyAddressChangeResponse)
async def change_address(
    body: ApplyAddressChangeRequest,
    _: None = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(_get_redis),
) -> ApplyAddressChangeResponse:
    """Применяет смену адреса с mock-оплатой доплаты."""
    repo = OmsRepository(session)
    order = await repo.get_by_id(body.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    if not can_change_address(order.status):
        return ApplyAddressChangeResponse(
            ok=False,
            message=address_change_denied_reason(order.status),
        )

    quote = quote_address_change(body.address)
    if not quote.ok:
        return ApplyAddressChangeResponse(ok=False, message=quote.message)

    payments = MockPaymentGateway(redis)
    pay = await payments.charge(
        amount=quote.surcharge,
        order_id=order.id,
        idempotency_key=body.idempotency_key,
        description=f"Доплата за смену адреса {order.id}",
    )
    if not pay.ok:
        return ApplyAddressChangeResponse(ok=False, message=pay.message)

    order.address = quote.normalized_address
    order.total_amount = Decimal(order.total_amount) + quote.surcharge
    await session.flush()

    return ApplyAddressChangeResponse(
        ok=True,
        message=(
            f"Адрес обновлён. {pay.message}"
            if quote.surcharge > 0
            else "Адрес обновлён без доплаты."
        ),
        payment_id=pay.payment_id,
        surcharge=quote.surcharge,
        order=to_order_dto(order),
    )


@router.post("/orders/change-slot", response_model=ApplySlotChangeResponse)
async def change_slot(
    body: ApplySlotChangeRequest,
    _: None = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> ApplySlotChangeResponse:
    """Меняет слот/время доставки."""
    repo = OmsRepository(session)
    order = await repo.get_by_id(body.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    if not can_change_time(order.status):
        return ApplySlotChangeResponse(
            ok=False,
            message=(
                "Время уже нельзя изменить — заказ передан курьеру " "или дальше по процессу."
            ),
        )

    slot = find_slot(body.slot_id)
    if slot is None:
        return ApplySlotChangeResponse(ok=False, message="Неизвестный слот доставки.")

    order.delivery_slot = slot.label
    await session.flush()
    return ApplySlotChangeResponse(
        ok=True,
        message=f"Время доставки изменено на «{slot.label}».",
        order=to_order_dto(order),
    )
