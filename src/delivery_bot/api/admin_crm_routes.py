"""Admin API для mock CRM (ответы оператора)."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from delivery_bot.api.oms_routes import get_db_session
from delivery_bot.config import Settings, get_settings
from delivery_bot.integrations.crm.repository import CrmRepository
from delivery_bot.integrations.crm.schemas import (
    EscalationTicketDTO,
    OperatorReplyRequest,
)

router = APIRouter(prefix="/admin/v1/tickets", tags=["admin-crm"])
security = HTTPBasic()


def _require_admin(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
    settings: Settings = Depends(get_settings),
) -> None:
    user_ok = secrets.compare_digest(
        credentials.username.encode(),
        settings.admin_basic_user.encode(),
    )
    pass_ok = secrets.compare_digest(
        credentials.password.encode(),
        settings.admin_basic_password.encode(),
    )
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )


@router.get("", response_model=list[EscalationTicketDTO])
async def admin_list_tickets(
    status_filter: str | None = None,
    _: None = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[EscalationTicketDTO]:
    return await CrmRepository(session).list_tickets(status=status_filter)


@router.get("/{ticket_id}", response_model=EscalationTicketDTO)
async def admin_get_ticket(
    ticket_id: int,
    _: None = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> EscalationTicketDTO:
    ticket = await CrmRepository(session).get_ticket_dto(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return ticket


@router.post("/{ticket_id}/reply", status_code=201)
async def admin_reply(
    ticket_id: int,
    body: OperatorReplyRequest,
    _: None = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, int | str]:
    repo = CrmRepository(session)
    msg = await repo.add_message(
        ticket_id,
        sender="operator",
        body=body.body,
        delivered=False,
    )
    if msg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return {"message_id": msg.id, "status": "queued"}


@router.post("/{ticket_id}/resolve", response_model=EscalationTicketDTO)
async def admin_resolve(
    ticket_id: int,
    _: None = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> EscalationTicketDTO:
    ticket = await CrmRepository(session).resolve_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return ticket
