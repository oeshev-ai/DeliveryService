"""Оркестрация ответа FAQ: keyword + опциональный LLM."""

from __future__ import annotations

from delivery_bot.integrations.faq.schemas import (
    FaqArticleDTO,
    FaqAskResponse,
)
from delivery_bot.integrations.faq.search import search_articles
from delivery_bot.integrations.llm import LlmClient
from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)

# Пороги уверенности
_HIGH = 0.55
_LOW = 0.28


async def answer_question(
    question: str,
    articles: list[FaqArticleDTO],
    *,
    llm: LlmClient | None = None,
    llm_enabled: bool = False,
) -> FaqAskResponse:
    """Отвечает на вопрос по KB; при low confidence — escalate."""
    search = search_articles(question, articles, limit=5, min_score=0.12)
    suggestions = [h.article for h in search.hits[:3]]

    # 1) Сильный keyword-hit — сразу отдаём статью
    if search.best and search.best.score >= _HIGH:
        return FaqAskResponse(
            ok=True,
            answer=search.best.article.answer,
            confidence=search.best.score,
            source="keyword",
            article_id=search.best.article.id,
            suggestions=suggestions,
            escalate=False,
        )

    # 2) LLM по топ-статьям (если включён)
    if llm_enabled and llm is not None and llm.configured and search.hits:
        ctx = [h.article for h in search.hits]
        llm_result = await llm.answer_from_kb(question, ctx)
        logger.info(
            "faq_llm_result",
            ok=llm_result.ok,
            confidence=llm_result.confidence,
            article_id=llm_result.article_id,
        )
        if llm_result.ok and llm_result.confidence >= _HIGH:
            return FaqAskResponse(
                ok=True,
                answer=llm_result.answer,
                confidence=llm_result.confidence,
                source="llm",
                article_id=llm_result.article_id,
                suggestions=suggestions,
                escalate=False,
            )
        if llm_result.ok and llm_result.confidence >= _LOW:
            return FaqAskResponse(
                ok=True,
                answer=llm_result.answer,
                confidence=llm_result.confidence,
                source="llm",
                article_id=llm_result.article_id,
                suggestions=suggestions,
                escalate=llm_result.confidence < _HIGH,
            )

    # 3) Средний keyword — показать лучший ответ + подсказки
    if search.best and search.best.score >= _LOW:
        return FaqAskResponse(
            ok=True,
            answer=search.best.article.answer,
            confidence=search.best.score,
            source="keyword",
            article_id=search.best.article.id,
            suggestions=suggestions,
            escalate=search.best.score < _HIGH,
        )

    # 4) Ничего подходящего
    return FaqAskResponse(
        ok=False,
        answer=(
            "Не нашёл точного ответа в базе знаний.\n"
            "Выберите тему ниже или свяжитесь с оператором."
        ),
        confidence=search.best.score if search.best else 0.0,
        source="none",
        article_id=None,
        suggestions=suggestions or articles[:3],
        escalate=True,
    )
