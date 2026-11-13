"""Репозиторий претензий и отзывов."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from delivery_bot.db.models import ClaimModel, ReviewModel
from delivery_bot.integrations.oms.post_delivery_schemas import (
    ClaimDTO,
    CreateClaimRequest,
    ReviewDTO,
    SkipReviewRequest,
    SubmitReviewRequest,
)


def claim_to_dto(row: ClaimModel) -> ClaimDTO:
    return ClaimDTO(
        id=row.id,
        order_id=row.order_id,
        reason_code=row.reason_code,
        description=row.description,
        status=row.status,
        photo_url=row.photo_url,
    )


def review_to_dto(row: ReviewModel) -> ReviewDTO:
    return ReviewDTO(
        id=row.id,
        order_id=row.order_id,
        rating=row.rating,
        comment=row.comment,
        skipped=row.skipped,
    )


class PostDeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_claim_for_order(self, order_id: str, user_id: str) -> ClaimModel | None:
        return await self._session.scalar(
            select(ClaimModel).where(
                ClaimModel.order_id == order_id.upper(),
                ClaimModel.user_id == user_id,
            )
        )

    async def create_claim(self, body: CreateClaimRequest) -> ClaimModel:
        row = ClaimModel(
            order_id=body.order_id.upper(),
            channel=body.channel,
            user_id=body.user_id,
            reason_code=body.reason_code,
            description=body.description.strip(),
            photo_url=body.photo_url,
            status="open",
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_review(self, order_id: str, user_id: str) -> ReviewModel | None:
        return await self._session.scalar(
            select(ReviewModel).where(
                ReviewModel.order_id == order_id.upper(),
                ReviewModel.user_id == user_id,
            )
        )

    async def submit_review(self, body: SubmitReviewRequest) -> ReviewModel:
        existing = await self.get_review(body.order_id, body.user_id)
        if existing is not None:
            existing.rating = body.rating
            existing.comment = (body.comment or "").strip() or None
            existing.skipped = False
            await self._session.flush()
            return existing
        row = ReviewModel(
            order_id=body.order_id.upper(),
            channel=body.channel,
            user_id=body.user_id,
            rating=body.rating,
            comment=(body.comment or "").strip() or None,
            skipped=False,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def skip_review(self, body: SkipReviewRequest) -> ReviewModel:
        existing = await self.get_review(body.order_id, body.user_id)
        if existing is not None:
            return existing
        row = ReviewModel(
            order_id=body.order_id.upper(),
            channel=body.channel,
            user_id=body.user_id,
            rating=None,
            comment=None,
            skipped=True,
        )
        self._session.add(row)
        await self._session.flush()
        return row
