"""Схемы смены адреса/времени и доплаты."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from delivery_bot.integrations.oms.schemas import OrderDTO


class DeliverySlotDTO(BaseModel):
    id: str
    label: str


class DeliveryRulesDTO(BaseModel):
    min_order_amount: Decimal
    slots: list[DeliverySlotDTO]


class AddressQuoteRequest(BaseModel):
    order_id: str
    address: str = Field(min_length=5, max_length=500)


class AddressQuoteResponse(BaseModel):
    ok: bool
    in_zone: bool
    surcharge: Decimal
    message: str
    normalized_address: str
    can_change_address: bool


class ApplyAddressChangeRequest(BaseModel):
    order_id: str
    address: str = Field(min_length=5, max_length=500)
    idempotency_key: str = Field(min_length=8, max_length=64)


class ApplyAddressChangeResponse(BaseModel):
    ok: bool
    message: str
    payment_id: str | None = None
    surcharge: Decimal = Decimal("0")
    order: OrderDTO | None = None


class ApplySlotChangeRequest(BaseModel):
    order_id: str
    slot_id: str


class ApplySlotChangeResponse(BaseModel):
    ok: bool
    message: str
    order: OrderDTO | None = None
