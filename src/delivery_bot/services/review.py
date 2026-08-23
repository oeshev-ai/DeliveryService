"""Сценарий отзыва после доставки."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from delivery_bot.dialog.keyboards import main_menu_keyboard
from delivery_bot.dialog.manager import DialogResponse
from delivery_bot.dialog.session import DialogSession
from delivery_bot.dialog.states import DialogState
from delivery_bot.integrations.oms.cache import OrderStatusCache
from delivery_bot.integrations.oms.client import OmsClient, OmsError
from delivery_bot.integrations.oms.post_delivery_client import PostDeliveryClient
from delivery_bot.integrations.oms.post_delivery_schemas import (
    SkipReviewRequest,
    SubmitReviewRequest,
)
from delivery_bot.integrations.oms.schemas import OrderDTO
from delivery_bot.logging_setup import get_logger
from delivery_bot.services.order_policy import can_review

logger = get_logger(__name__)


def _rating_keyboard(*, order_id: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{n} ⭐",
                callback_data=f"review:rate:{n}",
            )
            for n in range(1, 4)
        ],
        [
            InlineKeyboardButton(
                text=f"{n} ⭐",
                callback_data=f"review:rate:{n}",
            )
            for n in range(4, 6)
        ],
        [
            InlineKeyboardButton(
                text="Пропустить",
                callback_data="review:skip",
            )
        ],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def review_offer_keyboard(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ Оставить отзыв",
                    callback_data="review:start",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Пропустить",
                    callback_data="review:skip",
                )
            ],
        ]
    )


class ReviewService:
    def __init__(
        self,
        oms: OmsClient,
        post_delivery: PostDeliveryClient,
        cache: OrderStatusCache,
    ) -> None:
        self._oms = oms
        self._post = post_delivery
        self._cache = cache

    async def start(self, session: DialogSession) -> DialogResponse:
        order_id = session.context.get("verified_order_id")
        if not order_id:
            session.state = DialogState.AWAITING_ORDER_ID
            session.context["after_verify"] = "review"
            return DialogResponse(
                text=(
                    "Для отзыва подтвердите доставленный заказ "
                    "(например <code>ORD-1004</code> + last4)."
                ),
            )
        return await self._offer(session, str(order_id))

    async def offer_for_order(
        self, session: DialogSession, order_id: str
    ) -> DialogResponse | None:
        """Предложение отзыва после показа статуса delivered."""
        try:
            status = await self._post.review_status(order_id, session.user_id)
        except Exception:
            return None
        if not status.can_review:
            return None
        session.context["review_order_id"] = order_id
        return DialogResponse(
            text=(
                f"Заказ <b>{order_id}</b> доставлен 🎉\n"
                "Оцените доставку от 1 до 5:"
            ),
            reply_markup=_rating_keyboard(order_id=order_id),
        )

    async def handle_callback(
        self, session: DialogSession, data: str
    ) -> DialogResponse:
        if data == "review:skip":
            return await self._skip(session)
        if data == "review:start":
            order_id = session.context.get("verified_order_id") or session.context.get(
                "review_order_id"
            )
            if not order_id:
                return await self.start(session)
            return await self._offer(session, str(order_id))
        if data.startswith("review:rate:"):
            rating = int(data.split(":")[-1])
            return await self._on_rating(session, rating)
        if data == "review:comment_skip":
            return await self._submit(session, "")
        return DialogResponse(text="Неизвестное действие.")

    async def handle_input(
        self, session: DialogSession, text: str
    ) -> DialogResponse:
        if session.context.get("review_rating") is not None:
            return await self._submit(session, text)
        return await self.start(session)

    async def _offer(self, session: DialogSession, order_id: str) -> DialogResponse:
        order = await self._load_order(session, order_id)
        if order is None:
            return DialogResponse(
                text="Заказ не найден.",
                reply_markup=main_menu_keyboard(),
            )
        if not can_review(order.status):
            return DialogResponse(
                text="Отзыв доступен только для доставленных заказов.",
                reply_markup=main_menu_keyboard(active_order_id=order.id),
            )
        try:
            status = await self._post.review_status(order.id, session.user_id)
        except Exception:
            return DialogResponse(
                text="Сервис отзывов недоступен.",
                reply_markup=main_menu_keyboard(active_order_id=order.id),
            )
        if not status.can_review:
            return DialogResponse(
                text="Отзыв по этому заказу уже был оставлен или пропущен.",
                reply_markup=main_menu_keyboard(active_order_id=order.id),
            )
        session.context["review_order_id"] = order.id
        session.state = DialogState.REVIEW
        return DialogResponse(
            text=f"Оцените заказ <b>{order.id}</b> от 1 до 5:",
            reply_markup=_rating_keyboard(order_id=order.id),
        )

    async def _on_rating(
        self, session: DialogSession, rating: int
    ) -> DialogResponse:
        session.context["review_rating"] = rating
        session.state = DialogState.REVIEW
        return DialogResponse(
            text=(
                f"Оценка: {'⭐' * rating}\n"
                "Можете добавить комментарий или нажмите «Пропустить»:"
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Пропустить комментарий",
                            callback_data="review:comment_skip",
                        )
                    ]
                ]
            ),
        )

    async def _submit(self, session: DialogSession, comment: str) -> DialogResponse:
        order_id = str(
            session.context.get("review_order_id")
            or session.context.get("verified_order_id")
            or ""
        )
        rating = session.context.get("review_rating")
        if not order_id or rating is None:
            return await self.start(session)
        try:
            result = await self._post.submit_review(
                SubmitReviewRequest(
                    order_id=order_id,
                    channel=session.channel,
                    user_id=session.user_id,
                    rating=int(rating),
                    comment=comment.strip(),
                )
            )
        except Exception:
            return DialogResponse(
                text="Не удалось сохранить отзыв.",
                reply_markup=main_menu_keyboard(active_order_id=order_id),
            )
        session.context.pop("review_rating", None)
        session.context.pop("review_order_id", None)
        session.state = DialogState.MAIN_MENU
        return DialogResponse(
            text=result.message,
            reply_markup=main_menu_keyboard(active_order_id=order_id),
        )

    async def _skip(self, session: DialogSession) -> DialogResponse:
        order_id = str(
            session.context.get("review_order_id")
            or session.context.get("verified_order_id")
            or ""
        )
        if not order_id:
            session.state = DialogState.MAIN_MENU
            return DialogResponse(
                text="Хорошо.",
                reply_markup=main_menu_keyboard(),
            )
        try:
            result = await self._post.skip_review(
                SkipReviewRequest(
                    order_id=order_id,
                    channel=session.channel,
                    user_id=session.user_id,
                )
            )
        except Exception:
            return DialogResponse(
                text="Не удалось сохранить выбор.",
                reply_markup=main_menu_keyboard(active_order_id=order_id),
            )
        session.context.pop("review_rating", None)
        session.context.pop("review_order_id", None)
        session.state = DialogState.MAIN_MENU
        return DialogResponse(
            text=result.message,
            reply_markup=main_menu_keyboard(active_order_id=order_id),
        )

    async def _load_order(
        self, session: DialogSession, order_id: str
    ) -> OrderDTO | None:
        cached = await self._cache.get(order_id)
        if cached:
            return cached
        last4 = session.context.get("phone_last4")
        if not last4:
            return None
        try:
            result = await self._oms.verify(order_id, str(last4))
        except OmsError:
            return None
        if result.ok and result.order:
            await self._cache.set(result.order)
            return result.order
        return None
