"""Тесты претензий, отзывов и reorder."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from delivery_bot.services.order_policy import can_reorder, can_review
from delivery_bot.services.post_delivery import (
    CLAIM_WINDOW_DAYS,
    build_reorder_preview,
    can_submit_claim,
    claim_denied_reason,
)


def test_can_review_only_delivered() -> None:
    assert can_review("delivered") is True
    assert can_review("delivering") is False


def test_can_reorder_delivered_or_cancelled() -> None:
    assert can_reorder("delivered") is True
    assert can_reorder("cancelled") is True
    assert can_reorder("paid") is False


def test_claim_window_14_days() -> None:
    now = datetime.now(UTC)
    recent = now - timedelta(days=5)
    old = now - timedelta(days=20)
    assert can_submit_claim(status="delivered", delivered_at=recent, now=now)
    assert not can_submit_claim(status="delivered", delivered_at=old, now=now)
    assert CLAIM_WINDOW_DAYS == 14
    assert "14" in claim_denied_reason(status="delivered", delivered_at=old, now=now)


@pytest.mark.asyncio
async def test_reorder_preview_skips_unavailable() -> None:
    order = SimpleNamespace(
        id="ORD-9001",
        status="delivered",
        address="Москва",
        delivery_slot="сегодня",
        items=[
            SimpleNamespace(
                name="Бургер",
                quantity=1,
                price=Decimal("450.00"),
                available=True,
            ),
            SimpleNamespace(
                name="Картофель",
                quantity=1,
                price=Decimal("200.00"),
                available=False,
            ),
        ],
    )
    session = MagicMock()
    repo = AsyncMock()
    repo.get_by_id.return_value = order

    import delivery_bot.services.post_delivery as pd

    original = pd.OmsRepository
    pd.OmsRepository = MagicMock(return_value=repo)
    try:
        preview = await build_reorder_preview(session, "ORD-9001")
    finally:
        pd.OmsRepository = original

    assert preview.ok is True
    assert preview.total_amount == Decimal("450.00")
    assert preview.skipped_items == ["Картофель"]
