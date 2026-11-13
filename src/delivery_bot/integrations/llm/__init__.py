"""OpenAI-compatible LLM клиент для FAQ (+ mock)."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass

import httpx

from delivery_bot.integrations.faq.schemas import FaqArticleDTO
from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LlmFaqResult:
    ok: bool
    answer: str
    confidence: float
    article_id: int | None
    raw: str = ""


_SYSTEM = (
    "Ты помощник службы доставки. Отвечай ТОЛЬКО на русском и ТОЛЬКО по "
    "переданным статьям FAQ. Если ответа нет в статьях — conf=0 и короткий отказ. "
    "Формат ответа строго JSON: "
    '{"answer":"...","confidence":0.0,"article_id":null_or_int}'
)


class LlmClient:
    """Клиент chat-completions (OpenAI-compatible)."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 8.0,
        mock_latency_ms: int = 0,
    ) -> None:
        self._api_key = api_key
        self._base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self._model = model
        self._timeout = timeout
        self._mock_latency_ms = mock_latency_ms
        self._client: httpx.AsyncClient | None = None

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def start(self) -> None:
        if not self.configured:
            return
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def answer_from_kb(
        self,
        question: str,
        articles: list[FaqArticleDTO],
    ) -> LlmFaqResult:
        """Генерирует ответ строго по KB-контексту."""
        if self._mock_latency_ms > 0:
            await asyncio.sleep(self._mock_latency_ms / 1000)

        if not self.configured or self._client is None:
            return LlmFaqResult(
                ok=False,
                answer="",
                confidence=0.0,
                article_id=None,
            )

        context = "\n\n".join(
            (f"[id={a.id}] {a.title}\n" f"Q: {a.question}\n" f"A: {a.answer}") for a in articles[:6]
        )
        payload = {
            "model": self._model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": (f"Статьи FAQ:\n{context}\n\n" f"Вопрос клиента: {question}"),
                },
            ],
        }
        try:
            resp = await self._client.post("/chat/completions", json=payload)
        except httpx.HTTPError as exc:
            logger.warning("llm_request_failed", error=str(exc))
            return LlmFaqResult(ok=False, answer="", confidence=0.0, article_id=None)

        if resp.status_code >= 400:
            logger.warning("llm_http_error", status=resp.status_code, body=resp.text[:200])
            return LlmFaqResult(ok=False, answer="", confidence=0.0, article_id=None)

        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return _parse_llm_json(content, {a.id for a in articles})


class MockLlmClient(LlmClient):
    """LLM-заглушка: берёт лучшую keyword-статью без внешнего API."""

    def __init__(self, *, mock_latency_ms: int = 50) -> None:
        super().__init__(
            api_key="mock",
            base_url="http://localhost",
            model="mock",
            mock_latency_ms=mock_latency_ms,
        )
        self._force_mock = True

    @property
    def configured(self) -> bool:
        return True

    async def start(self) -> None:
        return None

    async def aclose(self) -> None:
        return None

    async def answer_from_kb(
        self,
        question: str,
        articles: list[FaqArticleDTO],
    ) -> LlmFaqResult:
        from delivery_bot.integrations.faq.search import search_articles

        if self._mock_latency_ms > 0:
            await asyncio.sleep(self._mock_latency_ms / 1000)
        result = search_articles(question, articles, limit=1, min_score=0.25)
        if result.best is None:
            return LlmFaqResult(
                ok=False,
                answer="В базе знаний нет подходящего ответа.",
                confidence=0.1,
                article_id=None,
            )
        hit = result.best
        return LlmFaqResult(
            ok=True,
            answer=hit.article.answer,
            confidence=min(0.95, 0.5 + hit.score / 2),
            article_id=hit.article.id,
            raw="mock",
        )


def _parse_llm_json(content: str, allowed_ids: set[int]) -> LlmFaqResult:
    text = content.strip()
    # вырезать ```json ... ```
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return LlmFaqResult(
            ok=False,
            answer=content.strip()[:800],
            confidence=0.2,
            article_id=None,
            raw=content,
        )

    answer = str(data.get("answer") or "").strip()
    try:
        confidence = float(data.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    article_id = data.get("article_id")
    try:
        article_id_int = int(article_id) if article_id is not None else None
    except (TypeError, ValueError):
        article_id_int = None
    if article_id_int is not None and article_id_int not in allowed_ids:
        article_id_int = None

    return LlmFaqResult(
        ok=bool(answer) and confidence >= 0.35,
        answer=answer,
        confidence=max(0.0, min(1.0, confidence)),
        article_id=article_id_int,
        raw=content,
    )
