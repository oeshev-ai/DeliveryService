"""Репозиторий заказов для mock OMS (чтение из PostgreSQL)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from delivery_bot.db.models import OrderModel
from delivery_bot.integrations.oms.schemas import (
    OrderDTO,
    OrderItemDTO,
    OrderPublicDTO,
    OrderSummaryDTO,
)
from delivery_bot.services.order_policy import OrderStatus

_IN_TRANSIT = {
    OrderStatus.HANDED_TO_COURIER.value,
    OrderStatus.DELIVERING.value,
}


def phone_last4(phone: str) -> str:
    """Возвращает последние 4 цифры телефона."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    return digits[-4:] if len(digits) >= 4 else digits


def to_order_dto(order: OrderModel) -> OrderDTO:
    """ORM → DTO."""
    return OrderDTO(
        id=order.id,
        status=order.status,
        address=order.address,
        delivery_slot=order.delivery_slot,
        eta_minutes=order.eta_minutes,
        courier_name=order.courier_name,
        courier_phone=order.courier_phone,
        total_amount=order.total_amount,
        phone_last4=phone_last4(order.phone),
        items=[
            OrderItemDTO(
                id=i.id,
                name=i.name,
                quantity=i.quantity,
                price=i.price,
                available=i.available,
            )
            for i in order.items
        ],
    )


class OmsRepository:
    """Доступ к заказам в БД (серверная сторона mock OMS)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, order_id: str) -> OrderModel | None:
        stmt = (
            select(OrderModel)
            .where(OrderModel.id == order_id.upper())
            .options(selectinload(OrderModel.items))
        )
        return await self._session.scalar(stmt)

    async def get_public(self, order_id: str) -> OrderPublicDTO | None:
        order = await self.get_by_id(order_id)
        if order is None:
            return None
        in_transit = order.status in _IN_TRANSIT
        return OrderPublicDTO(
            id=order.id,
            in_transit=in_transit,
            status_label="в пути" if in_transit else "не в пути",
        )

    async def verify(self, order_id: str, last4: str) -> OrderDTO | None:
        order = await self.get_by_id(order_id)
        if order is None:
            return None
        if phone_last4(order.phone) != last4:
            return None
        return to_order_dto(order)

    async def list_by_last4(self, last4: str, *, limit: int = 10) -> list[OrderSummaryDTO]:
        stmt = select(OrderModel).order_by(OrderModel.created_at.desc()).limit(100)
        rows = (await self._session.scalars(stmt)).all()
        matched = [o for o in rows if phone_last4(o.phone) == last4][:limit]
        return [
            OrderSummaryDTO(
                id=o.id,
                status=o.status,
                eta_minutes=o.eta_minutes,
                total_amount=o.total_amount,
            )
            for o in matched
        ]
