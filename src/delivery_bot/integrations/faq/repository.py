"""Репозиторий FAQ статей."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from delivery_bot.db.models import FaqArticleModel
from delivery_bot.integrations.faq.schemas import (
    FaqArticleCreate,
    FaqArticleDTO,
    FaqArticleUpdate,
)


def to_dto(row: FaqArticleModel) -> FaqArticleDTO:
    return FaqArticleDTO(
        id=row.id,
        slug=row.slug,
        title=row.title,
        category=row.category,
        question=row.question,
        answer=row.answer,
        keywords=row.keywords,
        is_active=row.is_active,
    )


class FaqRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self) -> list[FaqArticleDTO]:
        result = await self._session.scalars(
            select(FaqArticleModel)
            .where(FaqArticleModel.is_active.is_(True))
            .order_by(FaqArticleModel.category, FaqArticleModel.id)
        )
        return [to_dto(r) for r in result.all()]

    async def list_all(self) -> list[FaqArticleDTO]:
        result = await self._session.scalars(select(FaqArticleModel).order_by(FaqArticleModel.id))
        return [to_dto(r) for r in result.all()]

    async def get(self, article_id: int) -> FaqArticleModel | None:
        return await self._session.get(FaqArticleModel, article_id)

    async def get_by_slug(self, slug: str) -> FaqArticleModel | None:
        return await self._session.scalar(
            select(FaqArticleModel).where(FaqArticleModel.slug == slug)
        )

    async def create(self, data: FaqArticleCreate) -> FaqArticleModel:
        row = FaqArticleModel(**data.model_dump())
        self._session.add(row)
        await self._session.flush()
        return row

    async def update(self, row: FaqArticleModel, data: FaqArticleUpdate) -> FaqArticleModel:
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        await self._session.flush()
        return row

    async def soft_delete(self, row: FaqArticleModel) -> None:
        row.is_active = False
        await self._session.flush()
