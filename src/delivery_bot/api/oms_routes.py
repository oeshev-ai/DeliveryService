"""HTTP-роуты mock OMS."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from delivery_bot.config import Settings, get_settings
from delivery_bot.integrations.oms.repository import OmsRepository, to_order_dto
from delivery_bot.integrations.oms.schemas import (
    OrderDTO,
    OrderPublicDTO,
    OrderSummaryDTO,
    VerifyRequest,
    VerifyResponse,
)

router = APIRouter(prefix="/oms/v1", tags=["oms"])


async def _require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if not x_api_key or x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Сессия БД из lifespan FastAPI."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@router.get("/orders/{order_id}/public", response_model=OrderPublicDTO)
async def get_order_public(
    order_id: str,
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> OrderPublicDTO:
    """Без верификации: только факт «заказ в пути»."""
    repo = OmsRepository(session)
    public = await repo.get_public(order_id)
    if public is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return public


@router.get("/orders/{order_id}", response_model=OrderDTO)
async def get_order(
    order_id: str,
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> OrderDTO:
    """Полный заказ (для внутренних сервисов после verify)."""
    repo = OmsRepository(session)
    order = await repo.get_by_id(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return to_order_dto(order)


@router.post("/orders/verify", response_model=VerifyResponse)
async def verify_order(
    body: VerifyRequest,
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> VerifyResponse:
    """Верификация: номер заказа + последние 4 цифры телефона."""
    repo = OmsRepository(session)
    order = await repo.verify(body.order_id.strip().upper(), body.phone_last4)
    if order is None:
        return VerifyResponse(ok=False, reason="not_found_or_mismatch")
    return VerifyResponse(ok=True, order=order)


@router.get("/orders", response_model=list[OrderSummaryDTO])
async def list_orders(
    phone_last4: Annotated[str, Query(min_length=4, max_length=4, pattern=r"^\d{4}$")],
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> list[OrderSummaryDTO]:
    """Список заказов по last4 телефона."""
    repo = OmsRepository(session)
    return await repo.list_by_last4(phone_last4)
