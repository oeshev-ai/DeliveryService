"""Схемы ответов WebApp API."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class WebAppOrderView(BaseModel):
    """Данные виджета статуса для Mini App."""

    id: str
    status: str
    status_label: str
    status_color: str = Field(description="HEX цвет индикатора статуса")
    eta_minutes: int | None = None
    delivery_slot: str | None = None
    address: str
    total_amount: Decimal
    courier_name: str | None = None
    items_count: int = 0
