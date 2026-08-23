"""HTTP-клиент mock CRM для бота."""

from __future__ import annotations

import httpx

from delivery_bot.integrations.crm.schemas import (
    AddEscalationMessageRequest,
    CreateEscalationTicketRequest,
    EscalationTicketDTO,
)
from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)


class CrmError(Exception):
    """Ошибка вызова CRM API."""


class CrmClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 5.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            headers={"X-API-Key": self._api_key},
        )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise CrmError("CRM client is not started")
        return self._client

    async def get_active_ticket(
        self,
        *,
        channel: str,
        user_id: str,
    ) -> EscalationTicketDTO | None:
        try:
            resp = await self._http().get(
                "/crm/v1/tickets/active",
                params={"channel": channel, "user_id": user_id},
            )
        except httpx.HTTPError as exc:
            raise CrmError("CRM unavailable") from exc
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise CrmError(f"CRM error {resp.status_code}")
        return EscalationTicketDTO.model_validate(resp.json())

    async def create_ticket(
        self,
        payload: CreateEscalationTicketRequest,
    ) -> EscalationTicketDTO:
        try:
            resp = await self._http().post(
                "/crm/v1/tickets",
                json=payload.model_dump(),
            )
        except httpx.HTTPError as exc:
            raise CrmError("CRM unavailable") from exc
        if resp.status_code >= 400:
            raise CrmError(f"CRM error {resp.status_code}: {resp.text}")
        return EscalationTicketDTO.model_validate(resp.json())

    async def add_message(
        self,
        ticket_id: int,
        payload: AddEscalationMessageRequest,
    ) -> None:
        try:
            resp = await self._http().post(
                f"/crm/v1/tickets/{ticket_id}/messages",
                json=payload.model_dump(),
            )
        except httpx.HTTPError as exc:
            raise CrmError("CRM unavailable") from exc
        if resp.status_code >= 400:
            raise CrmError(f"CRM error {resp.status_code}")

    async def resolve_ticket(self, ticket_id: int) -> None:
        try:
            resp = await self._http().post(f"/crm/v1/tickets/{ticket_id}/resolve")
        except httpx.HTTPError as exc:
            raise CrmError("CRM unavailable") from exc
        if resp.status_code >= 400:
            raise CrmError(f"CRM error {resp.status_code}")
