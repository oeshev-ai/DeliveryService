"""Pydantic-схемы mock CRM."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class EscalationMessageDTO(BaseModel):
    id: int
    sender: str
    body: str
    delivered: bool
    created_at: datetime


class EscalationTicketDTO(BaseModel):
    id: int
    channel: str
    user_id: str
    order_id: str | None = None
    reason: str
    status: str
    transcript: str = ""
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    messages: list[EscalationMessageDTO] = Field(default_factory=list)


class CreateEscalationTicketRequest(BaseModel):
    channel: str = "telegram"
    user_id: str
    order_id: str | None = None
    reason: str = "operator"
    transcript: str = ""
    initial_message: str = Field(min_length=1, max_length=4000)


class AddEscalationMessageRequest(BaseModel):
    sender: str = Field(pattern=r"^(customer|operator|system)$")
    body: str = Field(min_length=1, max_length=4000)


class OperatorReplyRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
