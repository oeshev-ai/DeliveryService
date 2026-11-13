"""HTTP-клиент post-delivery API (claims, reviews, reorder)."""

from __future__ import annotations

import httpx

from delivery_bot.integrations.oms.post_delivery_schemas import (
    ClaimReasonDTO,
    ClaimResponse,
    CreateClaimRequest,
    ReorderConfirmRequest,
    ReorderConfirmResponse,
    ReorderPreviewResponse,
    ReviewResponse,
    ReviewStatusResponse,
    SkipReviewRequest,
    SubmitReviewRequest,
)
from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)


class PostDeliveryClient:
    """Клиент claims/reviews/reorder поверх mock OMS API."""

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
            raise RuntimeError("PostDeliveryClient is not started")
        return self._client

    async def list_claim_reasons(self) -> list[ClaimReasonDTO]:
        resp = await self._http().get("/oms/v1/claim-reasons")
        resp.raise_for_status()
        return [ClaimReasonDTO.model_validate(x) for x in resp.json()]

    async def create_claim(self, body: CreateClaimRequest) -> ClaimResponse:
        resp = await self._http().post(
            "/oms/v1/claims",
            json=body.model_dump(),
        )
        if resp.status_code == 404:
            return ClaimResponse(ok=False, message="Заказ не найден.")
        if resp.status_code >= 500:
            resp.raise_for_status()
        return ClaimResponse.model_validate(resp.json())

    async def review_status(self, order_id: str, user_id: str) -> ReviewStatusResponse:
        resp = await self._http().get(
            f"/oms/v1/orders/{order_id}/review-status",
            params={"user_id": user_id},
        )
        if resp.status_code == 404:
            raise ValueError("Order not found")
        resp.raise_for_status()
        return ReviewStatusResponse.model_validate(resp.json())

    async def submit_review(self, body: SubmitReviewRequest) -> ReviewResponse:
        resp = await self._http().post(
            "/oms/v1/reviews",
            json=body.model_dump(),
        )
        if resp.status_code == 404:
            return ReviewResponse(ok=False, message="Заказ не найден.")
        if resp.status_code >= 500:
            resp.raise_for_status()
        return ReviewResponse.model_validate(resp.json())

    async def skip_review(self, body: SkipReviewRequest) -> ReviewResponse:
        resp = await self._http().post(
            "/oms/v1/reviews/skip",
            json=body.model_dump(),
        )
        if resp.status_code >= 500:
            resp.raise_for_status()
        return ReviewResponse.model_validate(resp.json())

    async def reorder_preview(self, order_id: str) -> ReorderPreviewResponse:
        resp = await self._http().get(f"/oms/v1/orders/{order_id}/reorder-preview")
        if resp.status_code == 404:
            return ReorderPreviewResponse(
                ok=False,
                message="Заказ не найден.",
                source_order_id=order_id,
            )
        resp.raise_for_status()
        return ReorderPreviewResponse.model_validate(resp.json())

    async def confirm_reorder(self, body: ReorderConfirmRequest) -> ReorderConfirmResponse:
        resp = await self._http().post(
            "/oms/v1/orders/reorder",
            json=body.model_dump(mode="json"),
        )
        if resp.status_code >= 500:
            resp.raise_for_status()
        return ReorderConfirmResponse.model_validate(resp.json())
