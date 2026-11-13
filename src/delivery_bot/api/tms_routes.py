"""HTTP-роуты mock TMS / трекинг."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from delivery_bot.api.oms_routes import get_db_session
from delivery_bot.config import Settings, get_settings
from delivery_bot.integrations.oms.repository import OmsRepository
from delivery_bot.integrations.tms.mock import MockTmsService

router = APIRouter(prefix="/oms/v1", tags=["tms"])
_tms = MockTmsService()


class TrackingDTO(BaseModel):
    """Координаты доставки и курьера."""

    order_id: str
    status: str
    dest_lat: float
    dest_lon: float
    courier_lat: float | None
    courier_lon: float | None
    gps_available: bool
    courier_name: str | None
    courier_phone: str | None
    eta_minutes: int | None
    message: str | None = None


async def _require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if not x_api_key or x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


@router.get("/orders/{order_id}/tracking", response_model=TrackingDTO)
async def get_tracking(
    order_id: str,
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> TrackingDTO:
    """Трекинг курьера (mock TMS)."""
    repo = OmsRepository(session)
    order = await repo.get_by_id(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    point = _tms.tracking_for(
        order_id=order.id,
        status=order.status,
        courier_name=order.courier_name,
        courier_phone=order.courier_phone,
        eta_minutes=order.eta_minutes,
    )
    return TrackingDTO(
        order_id=point.order_id,
        status=point.status,
        dest_lat=point.dest_lat,
        dest_lon=point.dest_lon,
        courier_lat=point.courier_lat,
        courier_lon=point.courier_lon,
        gps_available=point.gps_available,
        courier_name=point.courier_name,
        courier_phone=point.courier_phone,
        eta_minutes=point.eta_minutes,
        message=point.message,
    )
