"""Публичный FAQ API для бота (поиск / ask)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from delivery_bot.api.oms_routes import get_db_session
from delivery_bot.config import Settings, get_settings
from delivery_bot.integrations.faq.repository import FaqRepository, to_dto
from delivery_bot.integrations.faq.schemas import (
    FaqArticleDTO,
    FaqAskRequest,
    FaqAskResponse,
    FaqSearchResponse,
)
from delivery_bot.integrations.faq.search import search_articles
from delivery_bot.integrations.llm import LlmClient
from delivery_bot.services.faq_engine import answer_question

router = APIRouter(prefix="/faq/v1", tags=["faq"])


async def _require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if not x_api_key or x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


def _llm_from_app(request: Request) -> LlmClient | None:
    return getattr(request.app.state, "llm", None)


@router.get("/articles", response_model=list[FaqArticleDTO])
async def list_articles(
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> list[FaqArticleDTO]:
    repo = FaqRepository(session)
    return await repo.list_active()


@router.get("/articles/{article_id}", response_model=FaqArticleDTO)
async def get_article(
    article_id: int,
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> FaqArticleDTO:
    repo = FaqRepository(session)
    row = await repo.get(article_id)
    if row is None or not row.is_active:
        raise HTTPException(status_code=404, detail="Article not found")
    return to_dto(row)


@router.get("/search", response_model=FaqSearchResponse)
async def search_faq(
    q: Annotated[str, Query(min_length=1, max_length=500)],
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> FaqSearchResponse:
    repo = FaqRepository(session)
    articles = await repo.list_active()
    result = search_articles(q, articles)
    return FaqSearchResponse(
        query=q,
        hits=result.hits,
        best=result.best,
    )


@router.post("/ask", response_model=FaqAskResponse)
async def ask_faq(
    body: FaqAskRequest,
    request: Request,
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> FaqAskResponse:
    repo = FaqRepository(session)
    articles = await repo.list_active()
    return await answer_question(
        body.question,
        articles,
        llm=_llm_from_app(request),
        llm_enabled=settings.llm_faq_enabled,
    )
