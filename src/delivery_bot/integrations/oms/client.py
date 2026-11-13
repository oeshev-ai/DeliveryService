"""HTTP-клиент mock OMS для бота."""

from __future__ import annotations

from typing import Any

import httpx

from delivery_bot.integrations.oms.cancel_schemas import (
    CancelReasonDTO,
    CancelResponse,
    FullCancelRequest,
    PartialCancelRequest,
)
from delivery_bot.integrations.oms.change_schemas import (
    AddressQuoteRequest,
    AddressQuoteResponse,
    ApplyAddressChangeRequest,
    ApplyAddressChangeResponse,
    ApplySlotChangeRequest,
    ApplySlotChangeResponse,
    DeliveryRulesDTO,
)
from delivery_bot.integrations.oms.schemas import (
    OrderDTO,
    OrderPublicDTO,
    OrderSummaryDTO,
    VerifyRequest,
    VerifyResponse,
)
from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)


class OmsError(Exception):
    """Ошибка вызова OMS."""


class OmsClient:
    """Клиент REST mock OMS (httpx)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 3.0,
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
            raise OmsError("OMS client is not started")
        return self._client

    async def get_order(self, order_id: str) -> OrderDTO | None:
        """Полный заказ (только для внутренних вызовов после verify на API)."""
        try:
            resp = await self._http().get(f"/oms/v1/orders/{order_id}")
        except httpx.HTTPError as exc:
            logger.warning("oms_get_order_failed", order_id=order_id, error=str(exc))
            raise OmsError("OMS unavailable") from exc

        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise OmsError(f"OMS error {resp.status_code}")
        return OrderDTO.model_validate(resp.json())

    async def get_public(self, order_id: str) -> OrderPublicDTO | None:
        try:
            resp = await self._http().get(f"/oms/v1/orders/{order_id}/public")
        except httpx.HTTPError as exc:
            logger.warning("oms_get_public_failed", order_id=order_id, error=str(exc))
            raise OmsError("OMS unavailable") from exc

        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise OmsError(f"OMS error {resp.status_code}")
        return OrderPublicDTO.model_validate(resp.json())

    async def verify(self, order_id: str, phone_last4: str) -> VerifyResponse:
        payload = VerifyRequest(order_id=order_id, phone_last4=phone_last4)
        try:
            resp = await self._http().post(
                "/oms/v1/orders/verify",
                json=payload.model_dump(),
            )
        except httpx.HTTPError as exc:
            logger.warning("oms_verify_failed", order_id=order_id, error=str(exc))
            raise OmsError("OMS unavailable") from exc

        if resp.status_code >= 500:
            raise OmsError(f"OMS error {resp.status_code}")
        data: dict[str, Any] = resp.json()
        return VerifyResponse.model_validate(data)

    async def list_by_last4(self, phone_last4: str) -> list[OrderSummaryDTO]:
        try:
            resp = await self._http().get(
                "/oms/v1/orders",
                params={"phone_last4": phone_last4},
            )
        except httpx.HTTPError as exc:
            logger.warning("oms_list_failed", error=str(exc))
            raise OmsError("OMS unavailable") from exc

        if resp.status_code >= 400:
            raise OmsError(f"OMS error {resp.status_code}")
        return [OrderSummaryDTO.model_validate(item) for item in resp.json()]

    async def get_delivery_rules(self) -> DeliveryRulesDTO:
        try:
            resp = await self._http().get("/oms/v1/delivery/rules")
        except httpx.HTTPError as exc:
            raise OmsError("OMS unavailable") from exc
        if resp.status_code >= 400:
            raise OmsError(f"OMS error {resp.status_code}")
        return DeliveryRulesDTO.model_validate(resp.json())

    async def quote_address(self, order_id: str, address: str) -> AddressQuoteResponse:
        payload = AddressQuoteRequest(order_id=order_id, address=address)
        try:
            resp = await self._http().post(
                "/oms/v1/orders/quote-address",
                json=payload.model_dump(mode="json"),
            )
        except httpx.HTTPError as exc:
            raise OmsError("OMS unavailable") from exc
        if resp.status_code >= 500:
            raise OmsError(f"OMS error {resp.status_code}")
        if resp.status_code == 404:
            raise OmsError("Order not found")
        return AddressQuoteResponse.model_validate(resp.json())

    async def change_address(
        self,
        order_id: str,
        address: str,
        idempotency_key: str,
    ) -> ApplyAddressChangeResponse:
        payload = ApplyAddressChangeRequest(
            order_id=order_id,
            address=address,
            idempotency_key=idempotency_key,
        )
        try:
            resp = await self._http().post(
                "/oms/v1/orders/change-address",
                json=payload.model_dump(mode="json"),
            )
        except httpx.HTTPError as exc:
            raise OmsError("OMS unavailable") from exc
        if resp.status_code >= 500:
            raise OmsError(f"OMS error {resp.status_code}")
        return ApplyAddressChangeResponse.model_validate(resp.json())

    async def change_slot(self, order_id: str, slot_id: str) -> ApplySlotChangeResponse:
        payload = ApplySlotChangeRequest(order_id=order_id, slot_id=slot_id)
        try:
            resp = await self._http().post(
                "/oms/v1/orders/change-slot",
                json=payload.model_dump(),
            )
        except httpx.HTTPError as exc:
            raise OmsError("OMS unavailable") from exc
        if resp.status_code >= 500:
            raise OmsError(f"OMS error {resp.status_code}")
        return ApplySlotChangeResponse.model_validate(resp.json())

    async def list_cancel_reasons(self) -> list[CancelReasonDTO]:
        try:
            resp = await self._http().get("/oms/v1/cancel-reasons")
        except httpx.HTTPError as exc:
            raise OmsError("OMS unavailable") from exc
        if resp.status_code >= 400:
            raise OmsError(f"OMS error {resp.status_code}")
        return [CancelReasonDTO.model_validate(item) for item in resp.json()]

    async def cancel_order(
        self,
        order_id: str,
        *,
        reason_code: str,
        comment: str,
        idempotency_key: str,
    ) -> CancelResponse:
        payload = FullCancelRequest(
            order_id=order_id,
            reason_code=reason_code,
            comment=comment,
            idempotency_key=idempotency_key,
        )
        try:
            resp = await self._http().post(
                "/oms/v1/orders/cancel",
                json=payload.model_dump(mode="json"),
            )
        except httpx.HTTPError as exc:
            raise OmsError("OMS unavailable") from exc
        if resp.status_code >= 500:
            raise OmsError(f"OMS error {resp.status_code}")
        if resp.status_code == 404:
            raise OmsError("Order not found")
        return CancelResponse.model_validate(resp.json())

    async def partial_cancel(
        self,
        order_id: str,
        *,
        item_ids: list[int],
        reason_code: str,
        comment: str,
        idempotency_key: str,
    ) -> CancelResponse:
        payload = PartialCancelRequest(
            order_id=order_id,
            item_ids=item_ids,
            reason_code=reason_code,
            comment=comment,
            idempotency_key=idempotency_key,
        )
        try:
            resp = await self._http().post(
                "/oms/v1/orders/partial-cancel",
                json=payload.model_dump(mode="json"),
            )
        except httpx.HTTPError as exc:
            raise OmsError("OMS unavailable") from exc
        if resp.status_code >= 500:
            raise OmsError(f"OMS error {resp.status_code}")
        if resp.status_code == 404:
            raise OmsError("Order not found")
        return CancelResponse.model_validate(resp.json())
