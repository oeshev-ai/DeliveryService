"""Keyword-поиск по статьям FAQ."""

from __future__ import annotations

import re
from dataclasses import dataclass

from delivery_bot.integrations.faq.schemas import FaqArticleDTO, FaqHitDTO


@dataclass(frozen=True, slots=True)
class SearchResult:
    hits: list[FaqHitDTO]
    best: FaqHitDTO | None


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\sа-яё/+-]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text


def score_article(query: str, article: FaqArticleDTO) -> float:
    """Оценивает релевантность статьи запросу (0…1)."""
    q = normalize_text(query)
    if not q:
        return 0.0

    keywords = [normalize_text(k) for k in article.keywords.split(",") if k.strip()]
    title = normalize_text(article.title)
    question = normalize_text(article.question)
    answer_head = normalize_text(article.answer[:200])

    score = 0.0
    if keywords:
        matched = sum(1 for kw in keywords if kw and kw in q)
        score += 0.55 * (matched / len(keywords))
        # бонус за точное вхождение длинных ключей
        for kw in keywords:
            if len(kw) >= 4 and kw in q:
                score += 0.08

    q_tokens = set(q.split())
    title_tokens = set(title.split())
    if q_tokens and title_tokens:
        overlap = len(q_tokens & title_tokens) / max(len(q_tokens), 1)
        score += 0.25 * overlap

    if any(tok in question for tok in q_tokens if len(tok) > 3):
        score += 0.12
    if any(tok in answer_head for tok in q_tokens if len(tok) > 3):
        score += 0.08

    # прямое вхождение title/question в query или наоборот
    if title and title in q:
        score += 0.2
    if q and (q in question or q in title):
        score += 0.15

    return min(1.0, score)


def search_articles(
    query: str,
    articles: list[FaqArticleDTO],
    *,
    limit: int = 5,
    min_score: float = 0.15,
) -> SearchResult:
    """Ранжирует активные статьи по keyword-score."""
    scored: list[FaqHitDTO] = []
    for article in articles:
        if not article.is_active:
            continue
        sc = score_article(query, article)
        if sc >= min_score:
            scored.append(FaqHitDTO(article=article, score=round(sc, 4)))
    scored.sort(key=lambda h: h.score, reverse=True)
    hits = scored[:limit]
    return SearchResult(hits=hits, best=hits[0] if hits else None)
