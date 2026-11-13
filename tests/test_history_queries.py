"""История заказов без N+1 (счётчик SQL-запросов)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from delivery_bot.config import get_settings
from delivery_bot.db.base import Base
from delivery_bot.db.models import OrderItemModel, OrderModel, ReviewModel
from delivery_bot.db.session import create_engine, create_session_factory, session_scope
from delivery_bot.integrations.oms.post_delivery_repository import PostDeliveryRepository
from delivery_bot.integrations.oms.repository import OmsRepository
from delivery_bot.services.order_policy import can_reorder, can_review
from delivery_bot.webapp.colors import status_label
from delivery_bot.webapp.schemas import WebAppHistoryItem


@pytest.mark.asyncio
async def test_history_uses_at_most_three_queries() -> None:
    """orders(+items selectin) + reviews IN ≤ 3 SQL statements."""
    get_settings.cache_clear()
    settings = get_settings()
    engine = create_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = create_session_factory(engine)
    phone = "+79001234567"
    user_id = "hist-user"

    async with session_scope(factory) as session:
        for i in range(1, 6):
            oid = f"ORD-H{i:03d}"
            session.add(
                OrderModel(
                    id=oid,
                    phone=phone,
                    status="delivered" if i % 2 else "paid",
                    address="Addr",
                    delivery_slot="slot",
                    total_amount=Decimal("100.00"),
                    items=[
                        OrderItemModel(
                            name=f"Item {i}",
                            quantity=1,
                            price=Decimal("100.00"),
                        )
                    ],
                )
            )
        session.add(
            ReviewModel(
                order_id="ORD-H001",
                channel="telegram",
                user_id=user_id,
                rating=5,
                skipped=False,
            )
        )

    statements: list[str] = []

    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(str(statement))

    event.listen(engine.sync_engine, "before_cursor_execute", _before_cursor_execute)
    try:
        async with session_scope(factory) as session:
            items = await _build_history(session, phone_last4="4567", user_id=user_id)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _before_cursor_execute)

    assert len(items) == 5
    assert len(statements) <= 3
    await engine.dispose()


async def _build_history(
    session: AsyncSession,
    *,
    phone_last4: str,
    user_id: str,
) -> list[WebAppHistoryItem]:
    """Логика get_order_history без Redis binding (для подсчёта SQL)."""
    repo = OmsRepository(session)
    review_repo = PostDeliveryRepository(session)
    orders = await repo.list_full_by_last4(phone_last4, limit=12)
    reviews = await review_repo.get_reviews_for_orders([o.id for o in orders], user_id)
    items: list[WebAppHistoryItem] = []
    for full in orders:
        review = reviews.get(full.id)
        submitted = review is not None and (review.rating is not None or review.skipped)
        items.append(
            WebAppHistoryItem(
                id=full.id,
                status=full.status,
                status_label=status_label(full.status),
                total_amount=full.total_amount,
                delivery_slot=full.delivery_slot,
                can_reorder=can_reorder(full.status),
                can_review=can_review(full.status) and not submitted,
            )
        )
    return items
