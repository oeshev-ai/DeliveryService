"""HTTP-клиент FAQ API для бота."""

from __future__ import annotations

from typing import Any

import httpx

from delivery_bot.integrations.faq.schemas import (
    FaqArticleDTO,
    FaqAskRequest,
    FaqAskResponse,
    FaqSearchResponse,
)
from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)


class FaqError(Exception):
    """Ошибка вызова FAQ API."""


class FaqClient:
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
            raise FaqError("FAQ client is not started")
        return self._client

    async def list_articles(self) -> list[FaqArticleDTO]:
        try:
            resp = await self._http().get("/faq/v1/articles")
        except httpx.HTTPError as exc:
            raise FaqError("FAQ unavailable") from exc
        if resp.status_code >= 400:
            raise FaqError(f"FAQ error {resp.status_code}")
        return [FaqArticleDTO.model_validate(x) for x in resp.json()]

    async def get_article(self, article_id: int) -> FaqArticleDTO | None:
        try:
            resp = await self._http().get(f"/faq/v1/articles/{article_id}")
        except httpx.HTTPError as exc:
            raise FaqError("FAQ unavailable") from exc
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise FaqError(f"FAQ error {resp.status_code}")
        return FaqArticleDTO.model_validate(resp.json())

    async def search(self, query: str) -> FaqSearchResponse:
        try:
            resp = await self._http().get(
                "/faq/v1/search", params={"q": query}
            )
        except httpx.HTTPError as exc:
            raise FaqError("FAQ unavailable") from exc
        if resp.status_code >= 400:
            raise FaqError(f"FAQ error {resp.status_code}")
        return FaqSearchResponse.model_validate(resp.json())

    async def ask(self, question: str) -> FaqAskResponse:
        payload = FaqAskRequest(question=question)
        try:
            resp = await self._http().post(
                "/faq/v1/ask",
                json=payload.model_dump(),
            )
        except httpx.HTTPError as exc:
            raise FaqError("FAQ unavailable") from exc
        if resp.status_code >= 500:
            raise FaqError(f"FAQ error {resp.status_code}")
        data: dict[str, Any] = resp.json()
        return FaqAskResponse.model_validate(data)
