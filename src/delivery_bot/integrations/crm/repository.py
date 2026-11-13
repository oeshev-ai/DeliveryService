"""Репозиторий тикетов эскалации (PostgreSQL)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from delivery_bot.db.models import EscalationMessageModel, EscalationTicketModel
from delivery_bot.integrations.crm.schemas import (
    EscalationMessageDTO,
    EscalationTicketDTO,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _message_dto(row: EscalationMessageModel) -> EscalationMessageDTO:
    return EscalationMessageDTO(
        id=row.id,
        sender=row.sender,
        body=row.body,
        delivered=row.delivered,
        created_at=row.created_at,
    )


def _ticket_dto(row: EscalationTicketModel) -> EscalationTicketDTO:
    return EscalationTicketDTO(
        id=row.id,
        channel=row.channel,
        user_id=row.user_id,
        order_id=row.order_id,
        reason=row.reason,
        status=row.status,
        transcript=row.transcript,
        created_at=row.created_at,
        updated_at=row.updated_at,
        resolved_at=row.resolved_at,
        messages=[_message_dto(m) for m in row.messages],
    )


class CrmRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_ticket(self, ticket_id: int) -> EscalationTicketModel | None:
        return cast(
            EscalationTicketModel | None,
            await self._session.scalar(
                select(EscalationTicketModel)
                .where(EscalationTicketModel.id == ticket_id)
                .options(selectinload(EscalationTicketModel.messages))
            ),
        )

    async def get_active_ticket(
        self,
        *,
        channel: str,
        user_id: str,
    ) -> EscalationTicketModel | None:
        return cast(
            EscalationTicketModel | None,
            await self._session.scalar(
                select(EscalationTicketModel)
                .where(
                    EscalationTicketModel.channel == channel,
                    EscalationTicketModel.user_id == user_id,
                    EscalationTicketModel.status.in_(("open", "assigned")),
                )
                .options(selectinload(EscalationTicketModel.messages))
                .order_by(EscalationTicketModel.id.desc())
                .limit(1)
            ),
        )

    async def get_ticket_dto(self, ticket_id: int) -> EscalationTicketDTO | None:
        row = await self.get_ticket(ticket_id)
        if row is None:
            return None
        return _ticket_dto(row)

    async def get_active_ticket_dto(
        self,
        *,
        channel: str,
        user_id: str,
    ) -> EscalationTicketDTO | None:
        row = await self.get_active_ticket(channel=channel, user_id=user_id)
        if row is None:
            return None
        return _ticket_dto(row)

    async def list_tickets(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[EscalationTicketDTO]:
        stmt = (
            select(EscalationTicketModel)
            .options(selectinload(EscalationTicketModel.messages))
            .order_by(EscalationTicketModel.updated_at.desc())
            .limit(limit)
        )
        if status:
            stmt = stmt.where(EscalationTicketModel.status == status)
        rows = (await self._session.scalars(stmt)).all()
        return [_ticket_dto(row) for row in rows]

    async def create_ticket(
        self,
        *,
        channel: str,
        user_id: str,
        order_id: str | None,
        reason: str,
        transcript: str,
        initial_message: str,
    ) -> EscalationTicketDTO:
        ticket = EscalationTicketModel(
            channel=channel,
            user_id=user_id,
            order_id=order_id,
            reason=reason,
            status="open",
            transcript=transcript,
        )
        ticket.messages.append(
            EscalationMessageModel(
                sender="customer",
                body=initial_message,
                delivered=True,
            )
        )
        self._session.add(ticket)
        await self._session.flush()
        await self._session.refresh(ticket, attribute_names=["messages"])
        return _ticket_dto(ticket)

    async def add_message(
        self,
        ticket_id: int,
        *,
        sender: str,
        body: str,
        delivered: bool = False,
    ) -> EscalationMessageDTO | None:
        ticket = await self.get_ticket(ticket_id)
        if ticket is None or ticket.status == "resolved":
            return None
        msg = EscalationMessageModel(
            ticket_id=ticket_id,
            sender=sender,
            body=body,
            delivered=delivered,
        )
        ticket.updated_at = _utcnow()
        if sender == "operator":
            ticket.status = "assigned"
        self._session.add(msg)
        await self._session.flush()
        return _message_dto(msg)

    async def resolve_ticket(self, ticket_id: int) -> EscalationTicketDTO | None:
        ticket = await self.get_ticket(ticket_id)
        if ticket is None:
            return None
        ticket.status = "resolved"
        ticket.resolved_at = _utcnow()
        ticket.updated_at = _utcnow()
        await self._session.flush()
        return _ticket_dto(ticket)

    async def list_undelivered_operator_messages(
        self,
        *,
        limit: int = 100,
    ) -> list[tuple[EscalationMessageModel, EscalationTicketModel]]:
        stmt = (
            select(EscalationMessageModel, EscalationTicketModel)
            .join(
                EscalationTicketModel,
                EscalationMessageModel.ticket_id == EscalationTicketModel.id,
            )
            .where(
                EscalationMessageModel.sender == "operator",
                EscalationMessageModel.delivered.is_(False),
                EscalationTicketModel.status != "resolved",
            )
            .order_by(EscalationMessageModel.id.asc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).all()
        return [(msg, ticket) for msg, ticket in rows]

    async def mark_delivered(self, message_id: int) -> None:
        msg = await self._session.get(EscalationMessageModel, message_id)
        if msg is not None:
            msg.delivered = True
