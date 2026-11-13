"""CRM API для бота (mock handoff)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from delivery_bot.api.auth import require_api_key
from delivery_bot.api.oms_routes import get_db_session
from delivery_bot.integrations.crm.repository import CrmRepository
from delivery_bot.integrations.crm.schemas import (
    AddEscalationMessageRequest,
    CreateEscalationTicketRequest,
    EscalationMessageDTO,
    EscalationTicketDTO,
)

router = APIRouter(prefix="/crm/v1", tags=["crm"])


@router.get("/tickets/active", response_model=EscalationTicketDTO)
async def get_active_ticket(
    channel: str,
    user_id: str,
    _: None = Depends(require_api_key),
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
    _: None = Depends(require_api_key),
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
    _: None = Depends(require_api_key),
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
    _: None = Depends(require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> EscalationTicketDTO:
    repo = CrmRepository(session)
    ticket = await repo.resolve_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return ticket
