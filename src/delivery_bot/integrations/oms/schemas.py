"""Pydantic-схемы контракта mock OMS."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class OrderItemDTO(BaseModel):
    """Позиция заказа."""

    id: int | None = None
    name: str
    quantity: int
    price: Decimal
    available: bool = True


class OrderDTO(BaseModel):
    """Полные данные заказа (после верификации)."""

    id: str
    status: str
    address: str
    delivery_slot: str | None = None
    eta_minutes: int | None = None
    courier_name: str | None = None
    courier_phone: str | None = None
    total_amount: Decimal
    phone_last4: str
    items: list[OrderItemDTO] = Field(default_factory=list)


class OrderPublicDTO(BaseModel):
    """Публичный минимум без верификации: только факт «в пути»."""

    id: str
    in_transit: bool
    status_label: str


class OrderSummaryDTO(BaseModel):
    """Краткая карточка для списка заказов."""

    id: str
    status: str
    eta_minutes: int | None = None
    total_amount: Decimal


class VerifyRequest(BaseModel):
    """Запрос верификации владения заказом."""

    order_id: str
    phone_last4: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$")


class VerifyResponse(BaseModel):
    """Результат верификации."""

    ok: bool
    order: OrderDTO | None = None
    reason: str | None = None
