"""Конкурентная вставка отзывов (UniqueConstraint order_id+user_id)."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from delivery_bot.config import get_settings
from delivery_bot.db.base import Base
from delivery_bot.db.models import OrderModel, ReviewModel
from delivery_bot.db.session import create_engine, create_session_factory, session_scope
from delivery_bot.integrations.oms.post_delivery_repository import PostDeliveryRepository
from delivery_bot.integrations.oms.post_delivery_schemas import SubmitReviewRequest


@pytest.mark.asyncio
async def test_parallel_submit_review_one_row() -> None:
    """Два параллельных submit_review → одна запись, оба вызова успешны."""
    get_settings.cache_clear()
    settings = get_settings()
    engine = create_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = create_session_factory(engine)
    order_id = "ORD-RACE1"
    user_id = "race-user"

    async with session_scope(factory) as session:
        session.add(
            OrderModel(
                id=order_id,
                phone="+79001112233",
                status="delivered",
                address="Test",
                delivery_slot="slot",
                total_amount=Decimal("100.00"),
            )
        )

    async def _submit(rating: int) -> ReviewModel:
        async with session_scope(factory) as session:
            repo = PostDeliveryRepository(session)
            return await repo.submit_review(
                SubmitReviewRequest(
                    order_id=order_id,
                    channel="telegram",
                    user_id=user_id,
                    rating=rating,
                    comment=f"rating-{rating}",
                )
            )

    results = await asyncio.gather(_submit(5), _submit(4))
    assert all(r.order_id == order_id and r.user_id == user_id for r in results)

    async with session_scope(factory) as session:
        count = await session.scalar(
            select(func.count())
            .select_from(ReviewModel)
            .where(
                ReviewModel.order_id == order_id,
                ReviewModel.user_id == user_id,
            )
        )
        assert count == 1

    await engine.dispose()
