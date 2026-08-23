"""API для Telegram WebApp (виджет статуса + трекинг)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from delivery_bot.api.oms_routes import get_db_session
from delivery_bot.config import Settings, get_settings
from delivery_bot.integrations.oms.repository import OmsRepository
from delivery_bot.integrations.tms.mock import MockTmsService
from delivery_bot.webapp.bindings import WebAppBindingStore
from delivery_bot.webapp.colors import status_color, status_label
from delivery_bot.webapp.schemas import WebAppOrderView
from delivery_bot.webapp.telegram_auth import (
    TelegramInitDataError,
    TelegramWebAppUser,
    validate_init_data,
)

router = APIRouter(prefix="/webapp/v1", tags=["webapp"])
_tms = MockTmsService()


async def get_redis(request: Request) -> Redis:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis is not configured",
        )
    return redis


async def get_webapp_user(
    request: Request,
    settings: Settings = Depends(get_settings),
    x_telegram_init_data: Annotated[str | None, Header(alias="X-Telegram-Init-Data")] = None,
    x_webapp_dev_user: Annotated[str | None, Header(alias="X-WebApp-Dev-User")] = None,
) -> TelegramWebAppUser:
    """Аутентификация Mini App: initData или dev-bypass."""
    if (
        settings.webapp_dev_bypass
        and settings.app_env in {"local", "test"}
        and x_webapp_dev_user
    ):
        return TelegramWebAppUser(id=int(x_webapp_dev_user), first_name="Dev")

    if not x_telegram_init_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Telegram-Init-Data required",
        )
    try:
        return validate_init_data(
            x_telegram_init_data,
            settings.telegram_bot_token,
            max_age_seconds=settings.webapp_init_data_max_age_seconds,
        )
    except TelegramInitDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


@router.get("/orders/{order_id}", response_model=WebAppOrderView)
async def get_webapp_order(
    order_id: str,
    user: TelegramWebAppUser = Depends(get_webapp_user),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> WebAppOrderView:
    """Статус заказа + трекинг для виджета/карты."""
    store = WebAppBindingStore(redis, ttl_seconds=settings.webapp_binding_ttl_seconds)
    oid = order_id.strip().upper()
    if not await store.can_access(str(user.id), oid):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Order is not linked to this user. Verify it in the bot first.",
        )

    repo = OmsRepository(session)
    order = await repo.get_by_id(oid)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    point = _tms.tracking_for(
        order_id=order.id,
        status=order.status,
        courier_name=order.courier_name,
        courier_phone=order.courier_phone,
        eta_minutes=order.eta_minutes,
    )

    return WebAppOrderView(
        id=order.id,
        status=order.status,
        status_label=status_label(order.status),
        status_color=status_color(order.status),
        eta_minutes=order.eta_minutes,
        delivery_slot=order.delivery_slot,
        address=order.address,
        total_amount=order.total_amount,
        courier_name=order.courier_name,
        courier_phone=order.courier_phone,
        items_count=len(order.items),
        dest_lat=point.dest_lat,
        dest_lon=point.dest_lon,
        courier_lat=point.courier_lat,
        courier_lon=point.courier_lon,
        gps_available=point.gps_available,
        tracking_message=point.message,
        yandex_maps_api_key=settings.yandex_maps_api_key or "",
    )
