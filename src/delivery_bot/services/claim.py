"""Сценарий претензии по заказу."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from delivery_bot.dialog.keyboards import main_menu_keyboard, operator_offer_keyboard
from delivery_bot.dialog.manager import DialogResponse
from delivery_bot.dialog.session import DialogSession
from delivery_bot.dialog.states import DialogState
from delivery_bot.integrations.oms.cache import OrderStatusCache
from delivery_bot.integrations.oms.client import OmsClient, OmsError
from delivery_bot.integrations.oms.post_delivery_client import PostDeliveryClient
from delivery_bot.integrations.oms.post_delivery_schemas import (
    CLAIM_REASONS,
    CreateClaimRequest,
)
from delivery_bot.integrations.oms.schemas import OrderDTO
from delivery_bot.logging_setup import get_logger
from delivery_bot.services.order_policy import can_claim

logger = get_logger(__name__)

_REASON_OTHER = "other"


def _reasons_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=label,
                callback_data=f"claim:reason:{code}",
            )
        ]
        for code, label in CLAIM_REASONS
    ]
    rows.append(
        [InlineKeyboardButton(text="❌ Отмена", callback_data="claim:abort")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Отправить",
                    callback_data="claim:confirm",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="claim:abort",
                )
            ],
        ]
    )


class ClaimService:
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
            session.context["after_verify"] = "claim"
            return DialogResponse(
                text=(
                    "Для претензии подтвердите заказ: номер "
                    "(например <code>ORD-1004</code>) и last4 телефона."
                ),
            )

        order = await self._load_order(session, str(order_id))
        if order is None:
            return DialogResponse(
                text="Не удалось загрузить заказ.",
                reply_markup=main_menu_keyboard(),
            )

        self._clear_pending(session)
        if not can_claim(order.status):
            return DialogResponse(
                text=(
                    f"Претензию можно подать только по доставленному заказу.\n"
                    f"Текущий статус: {order.status}."
                ),
                reply_markup=operator_offer_keyboard(active_order_id=order.id),
            )

        # delivered_at проверяется на API; здесь только статус
        session.state = DialogState.CLAIM
        session.context["claim_order_id"] = order.id
        return DialogResponse(
            text=(
                f"Претензия по заказу <b>{order.id}</b>.\n"
                "Выберите причину (окно — 14 дней после доставки):"
            ),
            reply_markup=_reasons_keyboard(),
        )

    async def handle_callback(
        self, session: DialogSession, data: str
    ) -> DialogResponse:
        if data == "claim:abort":
            self._clear_pending(session)
            session.state = DialogState.MAIN_MENU
            return DialogResponse(
                text="Претензия отменена.",
                reply_markup=main_menu_keyboard(
                    active_order_id=session.context.get("verified_order_id")
                ),
            )
        if data.startswith("claim:reason:"):
            code = data.split(":", 2)[-1]
            session.context["claim_reason"] = code
            session.state = DialogState.CLAIM
            if code == _REASON_OTHER:
                return DialogResponse(
                    text="Опишите проблему одним сообщением:",
                )
            return DialogResponse(
                text="Добавьте комментарий или отправьте «-» чтобы пропустить:",
            )
        if data == "claim:confirm":
            return await self._submit(session)
        return DialogResponse(text="Неизвестное действие.")

    async def handle_input(
        self, session: DialogSession, text: str
    ) -> DialogResponse:
        if session.state != DialogState.CLAIM:
            return await self.start(session)
        reason = session.context.get("claim_reason")
        if not reason:
            return await self.start(session)

        comment = (text or "").strip()
        if reason == _REASON_OTHER and not comment:
            return DialogResponse(text="Для «Другое» нужно описание.")
        if comment == "-":
            comment = ""
        session.context["claim_description"] = comment[:2000]
        session.state = DialogState.CLAIM
        label = dict(CLAIM_REASONS).get(str(reason), reason)
        return DialogResponse(
            text=(
                f"Заказ: {session.context.get('claim_order_id')}\n"
                f"Причина: {label}\n"
                f"Комментарий: {comment or '—'}\n\nОтправить претензию?"
            ),
            reply_markup=_confirm_keyboard(),
        )

    async def _submit(self, session: DialogSession) -> DialogResponse:
        order_id = str(session.context.get("claim_order_id") or "")
        reason = str(session.context.get("claim_reason") or "")
        desc = str(session.context.get("claim_description") or "")
        try:
            result = await self._post.create_claim(
                CreateClaimRequest(
                    order_id=order_id,
                    channel=session.channel,
                    user_id=session.user_id,
                    reason_code=reason,
                    description=desc,
                )
            )
        except Exception:
            return DialogResponse(
                text="Не удалось отправить претензию. Попробуйте позже.",
                reply_markup=main_menu_keyboard(active_order_id=order_id),
            )

        self._clear_pending(session)
        session.state = DialogState.MAIN_MENU
        return DialogResponse(
            text=result.message,
            reply_markup=main_menu_keyboard(active_order_id=order_id)
            if result.ok
            else operator_offer_keyboard(active_order_id=order_id),
        )

    def _clear_pending(self, session: DialogSession) -> None:
        for key in ("claim_reason", "claim_description", "claim_order_id"):
            session.context.pop(key, None)

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
