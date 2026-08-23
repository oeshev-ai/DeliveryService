"""Справочник причин отмены и схемы cancel/refund."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from delivery_bot.integrations.oms.schemas import OrderDTO


class CancelReasonCode(StrEnum):
    CHANGED_MIND = "changed_mind"
    WRONG_ADDRESS = "wrong_address"
    TOO_LONG = "too_long"
    DUPLICATE = "duplicate"
    OTHER = "other"


CANCEL_REASONS: list[tuple[str, str]] = [
    (CancelReasonCode.CHANGED_MIND.value, "Передумал(а)"),
    (CancelReasonCode.WRONG_ADDRESS.value, "Ошибка в адресе/заказе"),
    (CancelReasonCode.TOO_LONG.value, "Слишком долго ждать"),
    (CancelReasonCode.DUPLICATE.value, "Дубль заказа"),
    (CancelReasonCode.OTHER.value, "Другое"),
]


class CancelReasonDTO(BaseModel):
    code: str
    label: str


class FullCancelRequest(BaseModel):
    order_id: str
    reason_code: str
    comment: str = Field(default="", max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=64)


class PartialCancelRequest(BaseModel):
    order_id: str
    item_ids: list[int] = Field(min_length=1)
    reason_code: str
    comment: str = Field(default="", max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=64)


class CancelResponse(BaseModel):
    ok: bool
    message: str
    refund_id: str | None = None
    refund_amount: Decimal = Decimal("0")
    order: OrderDTO | None = None
