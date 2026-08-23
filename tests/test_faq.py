"""Тесты FAQ KB, поиска и engine."""

import pytest

from delivery_bot.db.seed_faq import _SEED
from delivery_bot.integrations.faq.schemas import FaqArticleDTO
from delivery_bot.integrations.faq.search import score_article, search_articles
from delivery_bot.integrations.llm import MockLlmClient, _parse_llm_json
from delivery_bot.services.faq_engine import answer_question


def _articles() -> list[FaqArticleDTO]:
    return [
        FaqArticleDTO(
            id=i + 1,
            slug=row["slug"],
            title=row["title"],
            category=row["category"],
            question=row["question"],
            answer=row["answer"],
            keywords=row["keywords"],
            is_active=True,
        )
        for i, row in enumerate(_SEED)
    ]


def test_seed_has_core_topics() -> None:
    slugs = {r["slug"] for r in _SEED}
    assert "delivery-zone" in slugs
    assert "min-order" in slugs
    assert "cancel-order" in slugs


def test_keyword_search_zone() -> None:
    result = search_articles("зона доставки москва", _articles())
    assert result.best is not None
    assert result.best.article.slug == "delivery-zone"
    assert result.best.score >= 0.4


def test_keyword_search_min_order() -> None:
    result = search_articles("какая минимальная сумма", _articles())
    assert result.best is not None
    assert result.best.article.slug == "min-order"


def test_score_irrelevant_is_low() -> None:
    articles = _articles()
    scores = [score_article("рецепт борща бабушки", a) for a in articles]
    assert max(scores) < 0.35


@pytest.mark.asyncio
async def test_answer_high_confidence_keyword() -> None:
    resp = await answer_question(
        "минимальная сумма заказа",
        _articles(),
        llm=None,
        llm_enabled=False,
    )
    assert resp.ok is True
    assert resp.source == "keyword"
    assert resp.escalate is False
    assert "500" in resp.answer


@pytest.mark.asyncio
async def test_answer_unknown_escalates() -> None:
    resp = await answer_question(
        "как приготовить суши дома",
        _articles(),
        llm=None,
        llm_enabled=False,
    )
    assert resp.escalate is True
    assert resp.source == "none"


@pytest.mark.asyncio
async def test_answer_with_mock_llm() -> None:
    llm = MockLlmClient(mock_latency_ms=0)
    resp = await answer_question(
        "где мой курьер сейчас",
        _articles(),
        llm=llm,
        llm_enabled=True,
    )
    assert resp.ok is True
    assert resp.source in {"keyword", "llm"}
    assert "курьер" in resp.answer.lower() or resp.article_id is not None


def test_parse_llm_json() -> None:
    raw = '```json\n{"answer":"Ок","confidence":0.9,"article_id":3}\n```'
    parsed = _parse_llm_json(raw, {1, 2, 3})
    assert parsed.ok is True
    assert parsed.article_id == 3
    assert parsed.confidence == 0.9
