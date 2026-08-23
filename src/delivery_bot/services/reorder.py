"""Сценарий повторного заказа из истории."""

from __future__ import annotations

from uuid import uuid4

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from delivery_bot.dialog.keyboards import main_menu_keyboard
from delivery_bot.dialog.manager import DialogResponse
from delivery_bot.dialog.session import DialogSession
from delivery_bot.dialog.states import DialogState
from delivery_bot.integrations.oms.cache import OrderStatusCache
from delivery_bot.integrations.oms.client import OmsClient, OmsError
from delivery_bot.integrations.oms.post_delivery_client import PostDeliveryClient
from delivery_bot.integrations.oms.post_delivery_schemas import ReorderConfirmRequest
from delivery_bot.integrations.oms.schemas import OrderSummaryDTO
from delivery_bot.logging_setup import get_logger
from delivery_bot.services.order_policy import can_reorder

logger = get_logger(__name__)


def _orders_keyboard(orders: list[OrderSummaryDTO]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{o.id} ({o.status}) — {o.total_amount} ₽",
                callback_data=f"reorder:pick:{o.id}",
            )
        ]
        for o in orders[:6]
        if can_reorder(o.status)
    ]
    rows.append(
        [InlineKeyboardButton(text="❌ Отмена", callback_data="reorder:abort")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data="reorder:confirm",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="reorder:abort",
                )
            ],
        ]
    )


class ReorderService:
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
        last4 = session.context.get("phone_last4")
        if not last4:
            session.state = DialogState.AWAITING_ORDER_ID
            session.context["after_verify"] = "reorder"
            return DialogResponse(
                text=(
                    "Чтобы повторить заказ, сначала подтвердите телефон "
                    "(номер заказа + last4, например ORD-1004 / 4567)."
                ),
            )

        try:
            orders = await self._oms.list_by_last4(str(last4))
        except OmsError:
            return DialogResponse(
                text="Не удалось загрузить историю заказов.",
                reply_markup=main_menu_keyboard(
                    active_order_id=session.context.get("verified_order_id")
                ),
            )

        eligible = [o for o in orders if can_reorder(o.status)]
        if not eligible:
            return DialogResponse(
                text=(
                    "В истории нет заказов для повтора "
                    "(нужен статус delivered или cancelled)."
                ),
                reply_markup=main_menu_keyboard(
                    active_order_id=session.context.get("verified_order_id")
                ),
            )

        session.state = DialogState.REORDER
        return DialogResponse(
            text="Выберите заказ для повторения:",
            reply_markup=_orders_keyboard(eligible),
        )

    async def handle_callback(
        self, session: DialogSession, data: str
    ) -> DialogResponse:
        if data == "reorder:abort":
            session.context.pop("reorder_source_id", None)
            session.context.pop("reorder_idem", None)
            session.state = DialogState.MAIN_MENU
            return DialogResponse(
                text="Повтор заказа отменён.",
                reply_markup=main_menu_keyboard(
                    active_order_id=session.context.get("verified_order_id")
                ),
            )
        if data.startswith("reorder:pick:"):
            order_id = data.split(":", 2)[-1]
            return await self._preview(session, order_id)
        if data == "reorder:confirm":
            return await self._confirm(session)
        return DialogResponse(text="Неизвестное действие.")

    async def _preview(
        self, session: DialogSession, order_id: str
    ) -> DialogResponse:
        try:
            preview = await self._post.reorder_preview(order_id)
        except Exception:
            return DialogResponse(
                text="Сервис повтора недоступен.",
                reply_markup=main_menu_keyboard(
                    active_order_id=session.context.get("verified_order_id")
                ),
            )
        if not preview.ok:
            return DialogResponse(
                text=preview.message,
                reply_markup=main_menu_keyboard(
                    active_order_id=session.context.get("verified_order_id")
                ),
            )
        session.context["reorder_source_id"] = preview.source_order_id
        session.context["reorder_idem"] = uuid4().hex
        session.state = DialogState.REORDER
        lines = [
            f"Повтор заказа <b>{preview.source_order_id}</b>",
            f"Адрес: {preview.address}",
            f"Слот: {preview.delivery_slot or '—'}",
            f"Сумма: {preview.total_amount} ₽",
        ]
        if preview.skipped_items:
            lines.append(
                "Пропущено (нет в наличии): "
                + ", ".join(preview.skipped_items)
            )
        lines.append("\nПодтвердить?")
        return DialogResponse(
            text="\n".join(lines),
            reply_markup=_confirm_keyboard(),
        )

    async def _confirm(self, session: DialogSession) -> DialogResponse:
        source_id = session.context.get("reorder_source_id")
        idem = session.context.get("reorder_idem") or uuid4().hex
        if not source_id:
            return await self.start(session)
        try:
            result = await self._post.confirm_reorder(
                ReorderConfirmRequest(
                    source_order_id=str(source_id),
                    channel=session.channel,
                    user_id=session.user_id,
                    idempotency_key=str(idem),
                )
            )
        except Exception:
            return DialogResponse(
                text="Не удалось создать заказ.",
                reply_markup=main_menu_keyboard(
                    active_order_id=session.context.get("verified_order_id")
                ),
            )

        session.context.pop("reorder_source_id", None)
        session.context.pop("reorder_idem", None)
        session.state = DialogState.MAIN_MENU

        if result.ok and result.order:
            await self._cache.set(result.order)
            session.context["verified_order_id"] = result.order.id
            return DialogResponse(
                text=result.message,
                reply_markup=main_menu_keyboard(active_order_id=result.order.id),
            )
        return DialogResponse(
            text=result.message,
            reply_markup=main_menu_keyboard(
                active_order_id=session.context.get("verified_order_id")
            ),
        )
