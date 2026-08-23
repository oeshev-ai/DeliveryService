"""Admin CRUD для FAQ knowledge base (HTTP Basic)."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from delivery_bot.api.oms_routes import get_db_session
from delivery_bot.config import Settings, get_settings
from delivery_bot.integrations.faq.repository import FaqRepository, to_dto
from delivery_bot.integrations.faq.schemas import (
    FaqArticleCreate,
    FaqArticleDTO,
    FaqArticleUpdate,
)

router = APIRouter(prefix="/admin/v1/faq", tags=["admin-faq"])
security = HTTPBasic()


def _require_admin(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
    settings: Settings = Depends(get_settings),
) -> None:
    user_ok = secrets.compare_digest(
        credentials.username.encode(),
        settings.admin_basic_user.encode(),
    )
    pass_ok = secrets.compare_digest(
        credentials.password.encode(),
        settings.admin_basic_password.encode(),
    )
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )


@router.get("/articles", response_model=list[FaqArticleDTO])
async def admin_list(
    _: None = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[FaqArticleDTO]:
    return await FaqRepository(session).list_all()


@router.get("/articles/{article_id}", response_model=FaqArticleDTO)
async def admin_get(
    article_id: int,
    _: None = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> FaqArticleDTO:
    row = await FaqRepository(session).get(article_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return to_dto(row)


@router.post(
    "/articles",
    response_model=FaqArticleDTO,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create(
    body: FaqArticleCreate,
    _: None = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> FaqArticleDTO:
    repo = FaqRepository(session)
    try:
        row = await repo.create(body)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Slug already exists") from exc
    return to_dto(row)


@router.put("/articles/{article_id}", response_model=FaqArticleDTO)
async def admin_update(
    article_id: int,
    body: FaqArticleUpdate,
    _: None = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> FaqArticleDTO:
    repo = FaqRepository(session)
    row = await repo.get(article_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    row = await repo.update(row, body)
    return to_dto(row)


@router.delete("/articles/{article_id}", response_model=FaqArticleDTO)
async def admin_delete(
    article_id: int,
    _: None = Depends(_require_admin),
    session: AsyncSession = Depends(get_db_session),
) -> FaqArticleDTO:
    repo = FaqRepository(session)
    row = await repo.get(article_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    await repo.soft_delete(row)
    return to_dto(row)
