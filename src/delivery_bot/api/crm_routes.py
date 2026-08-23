"""CRM API для бота (mock handoff)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from delivery_bot.api.oms_routes import get_db_session
from delivery_bot.config import Settings, get_settings
from delivery_bot.integrations.crm.repository import CrmRepository
from delivery_bot.integrations.crm.schemas import (
    AddEscalationMessageRequest,
    CreateEscalationTicketRequest,
    EscalationMessageDTO,
    EscalationTicketDTO,
)

router = APIRouter(prefix="/crm/v1", tags=["crm"])


async def _require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if not x_api_key or x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


@router.get("/tickets/active", response_model=EscalationTicketDTO)
async def get_active_ticket(
    channel: str,
    user_id: str,
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> EscalationTicketDTO:
    repo = CrmRepository(session)
    ticket = await repo.get_active_ticket_dto(channel=channel, user_id=user_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return ticket


@router.post("/tickets", response_model=EscalationTicketDTO, status_code=201)
async def create_ticket(
    body: CreateEscalationTicketRequest,
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> EscalationTicketDTO:
    repo = CrmRepository(session)
    existing = await repo.get_active_ticket(
        channel=body.channel,
        user_id=body.user_id,
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Active ticket #{existing.id} already exists",
        )
    return await repo.create_ticket(
        channel=body.channel,
        user_id=body.user_id,
        order_id=body.order_id,
        reason=body.reason,
        transcript=body.transcript,
        initial_message=body.initial_message,
    )


@router.post(
    "/tickets/{ticket_id}/messages",
    response_model=EscalationMessageDTO,
    status_code=201,
)
async def add_message(
    ticket_id: int,
    body: AddEscalationMessageRequest,
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> EscalationMessageDTO:
    repo = CrmRepository(session)
    delivered = body.sender == "customer"
    msg = await repo.add_message(
        ticket_id,
        sender=body.sender,
        body=body.body,
        delivered=delivered,
    )
    if msg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return msg


@router.post("/tickets/{ticket_id}/resolve", response_model=EscalationTicketDTO)
async def resolve_ticket(
    ticket_id: int,
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> EscalationTicketDTO:
    repo = CrmRepository(session)
    ticket = await repo.resolve_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return ticket
