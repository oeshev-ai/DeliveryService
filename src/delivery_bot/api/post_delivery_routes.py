"""API претензий, отзывов и повторного заказа."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from delivery_bot.api.oms_routes import get_db_session
from delivery_bot.config import Settings, get_settings
from delivery_bot.integrations.oms.post_delivery_repository import (
    PostDeliveryRepository,
    claim_to_dto,
    review_to_dto,
)
from delivery_bot.integrations.oms.post_delivery_schemas import (
    CLAIM_REASONS,
    ClaimReasonDTO,
    ClaimResponse,
    CreateClaimRequest,
    ReviewResponse,
    ReviewStatusResponse,
    ReorderConfirmRequest,
    ReorderConfirmResponse,
    ReorderPreviewResponse,
    SkipReviewRequest,
    SubmitReviewRequest,
)
from delivery_bot.integrations.oms.repository import OmsRepository
from delivery_bot.services.post_delivery import (
    build_reorder_preview,
    claim_denied_reason,
    confirm_reorder,
)
from delivery_bot.services.order_policy import can_review

router = APIRouter(prefix="/oms/v1", tags=["post-delivery"])

_REASON_LABELS = dict(CLAIM_REASONS)


async def _require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    if not x_api_key or x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


async def _get_redis(request: Request) -> Redis:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="Redis is not configured")
    return redis


@router.get("/claim-reasons", response_model=list[ClaimReasonDTO])
async def list_claim_reasons(
    _: None = Depends(_require_api_key),
) -> list[ClaimReasonDTO]:
    return [ClaimReasonDTO(code=c, label=l) for c, l in CLAIM_REASONS]


@router.post("/claims", response_model=ClaimResponse)
async def create_claim(
    body: CreateClaimRequest,
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimResponse:
    if body.reason_code not in _REASON_LABELS:
        return ClaimResponse(ok=False, message="Неизвестная причина претензии.")

    oms = OmsRepository(session)
    order = await oms.get_by_id(body.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    reason = claim_denied_reason(
        status=order.status, delivered_at=order.delivered_at
    )
    if reason:
        return ClaimResponse(ok=False, message=reason)

    repo = PostDeliveryRepository(session)
    existing = await repo.get_claim_for_order(body.order_id, body.user_id)
    if existing is not None:
        return ClaimResponse(
            ok=False,
            message="Претензия по этому заказу уже была подана.",
        )

    if body.reason_code == "other" and not (body.description or "").strip():
        return ClaimResponse(
            ok=False,
            message="Для причины «Другое» нужно описание проблемы.",
        )

    row = await repo.create_claim(body)
    label = _REASON_LABELS[body.reason_code]
    return ClaimResponse(
        ok=True,
        message=(
            f"Претензия #{row.id} принята и передана в отдел качества.\n"
            f"Заказ: {order.id}, причина: {label}."
        ),
        claim=claim_to_dto(row),
    )


@router.get("/orders/{order_id}/review-status", response_model=ReviewStatusResponse)
async def review_status(
    order_id: str,
    user_id: Annotated[str, Query(min_length=1)],
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> ReviewStatusResponse:
    oms = OmsRepository(session)
    order = await oms.get_by_id(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    repo = PostDeliveryRepository(session)
    review = await repo.get_review(order_id, user_id)
    submitted = review is not None and (
        review.rating is not None or review.skipped
    )
    return ReviewStatusResponse(
        order_id=order.id,
        can_review=can_review(order.status) and not submitted,
        already_submitted=submitted,
        review=review_to_dto(review) if review else None,
    )


@router.post("/reviews", response_model=ReviewResponse)
async def submit_review(
    body: SubmitReviewRequest,
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> ReviewResponse:
    oms = OmsRepository(session)
    order = await oms.get_by_id(body.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if not can_review(order.status):
        return ReviewResponse(
            ok=False,
            message="Отзыв можно оставить только по доставленному заказу.",
        )

    repo = PostDeliveryRepository(session)
    existing = await repo.get_review(body.order_id, body.user_id)
    if existing and existing.rating is not None:
        return ReviewResponse(
            ok=False,
            message="Отзыв по этому заказу уже был оставлен.",
            review=review_to_dto(existing),
        )

    row = await repo.submit_review(body)
    stars = "⭐" * body.rating
    return ReviewResponse(
        ok=True,
        message=f"Спасибо за оценку {stars}!",
        review=review_to_dto(row),
    )


@router.post("/reviews/skip", response_model=ReviewResponse)
async def skip_review(
    body: SkipReviewRequest,
    request: Request,
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(_get_redis),
    settings: Settings = Depends(get_settings),
) -> ReviewResponse:
    oms = OmsRepository(session)
    order = await oms.get_by_id(body.order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    repo = PostDeliveryRepository(session)
    existing = await repo.get_review(body.order_id, body.user_id)
    if existing and (existing.rating is not None or existing.skipped):
        return ReviewResponse(
            ok=True,
            message="Отзыв уже обработан ранее.",
            review=review_to_dto(existing),
        )

    row = await repo.skip_review(body)
    scheduled = await _schedule_review_reminder(
        redis,
        settings=settings,
        order_id=body.order_id,
        user_id=body.user_id,
        channel=body.channel,
    )
    return ReviewResponse(
        ok=True,
        message="Хорошо, напомним позже оставить отзыв.",
        review=review_to_dto(row),
        reminder_scheduled=scheduled,
    )


@router.get("/orders/{order_id}/reorder-preview", response_model=ReorderPreviewResponse)
async def reorder_preview(
    order_id: str,
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
) -> ReorderPreviewResponse:
    return await build_reorder_preview(session, order_id)


@router.post("/orders/reorder", response_model=ReorderConfirmResponse)
async def reorder_confirm(
    body: ReorderConfirmRequest,
    _: None = Depends(_require_api_key),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ReorderConfirmResponse:
    return await confirm_reorder(session, body, settings=settings)


async def _schedule_review_reminder(
    redis: Redis,
    *,
    settings: Settings,
    order_id: str,
    user_id: str,
    channel: str,
) -> bool:
    key = f"review:reminder:scheduled:{order_id}:{user_id}"
    if await redis.get(key):
        return False
    payload = f"{channel}:{user_id}:{order_id}"
    await redis.set(
        key,
        payload,
        ex=settings.review_reminder_delay_seconds * 2,
    )
    await redis.zadd(
        "review:reminder:queue",
        {payload: _defer_score(settings.review_reminder_delay_seconds)},
    )
    return True


def _defer_score(delay_seconds: int) -> float:
    import time

    return time.time() + delay_seconds
