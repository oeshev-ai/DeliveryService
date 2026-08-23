"""Схемы претензий, отзывов и повторного заказа."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

from delivery_bot.integrations.oms.schemas import OrderDTO, OrderItemDTO


class ClaimReasonCode(StrEnum):
    WRONG_ITEM = "wrong_item"
    QUALITY = "quality"
    MISSING = "missing"
    LATE = "late"
    OTHER = "other"


CLAIM_REASONS: list[tuple[str, str]] = [
    (ClaimReasonCode.WRONG_ITEM.value, "Не тот товар"),
    (ClaimReasonCode.QUALITY.value, "Качество / испорчено"),
    (ClaimReasonCode.MISSING.value, "Не хватает позиций"),
    (ClaimReasonCode.LATE.value, "Опоздание доставки"),
    (ClaimReasonCode.OTHER.value, "Другое"),
]


class ClaimReasonDTO(BaseModel):
    code: str
    label: str


class CreateClaimRequest(BaseModel):
    order_id: str
    channel: str = "telegram"
    user_id: str
    reason_code: str
    description: str = Field(default="", max_length=2000)
    photo_url: str | None = Field(default=None, max_length=512)


class ClaimDTO(BaseModel):
    id: int
    order_id: str
    reason_code: str
    description: str
    status: str
    photo_url: str | None = None


class ClaimResponse(BaseModel):
    ok: bool
    message: str
    claim: ClaimDTO | None = None


class SubmitReviewRequest(BaseModel):
    order_id: str
    channel: str = "telegram"
    user_id: str
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1000)


class SkipReviewRequest(BaseModel):
    order_id: str
    channel: str = "telegram"
    user_id: str


class ReviewDTO(BaseModel):
    id: int
    order_id: str
    rating: int | None
    comment: str | None
    skipped: bool


class ReviewStatusResponse(BaseModel):
    order_id: str
    can_review: bool
    already_submitted: bool
    review: ReviewDTO | None = None


class ReviewResponse(BaseModel):
    ok: bool
    message: str
    review: ReviewDTO | None = None
    reminder_scheduled: bool = False


class ReorderItemDTO(BaseModel):
    name: str
    quantity: int
    price: Decimal
    available: bool
    included: bool


class ReorderPreviewResponse(BaseModel):
    ok: bool
    message: str
    source_order_id: str
    items: list[ReorderItemDTO] = Field(default_factory=list)
    skipped_items: list[str] = Field(default_factory=list)
    total_amount: Decimal = Decimal("0")
    address: str = ""
    delivery_slot: str | None = None


class ReorderConfirmRequest(BaseModel):
    source_order_id: str
    channel: str = "telegram"
    user_id: str
    idempotency_key: str = Field(min_length=8, max_length=64)


class ReorderConfirmResponse(BaseModel):
    ok: bool
    message: str
    order: OrderDTO | None = None


class OrderHistoryItem(BaseModel):
    id: str
    status: str
    total_amount: Decimal
    delivery_slot: str | None = None
    delivered_at: str | None = None
    can_reorder: bool = False
    can_review: bool = False
    can_claim: bool = False
