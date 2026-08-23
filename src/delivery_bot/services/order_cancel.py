"""Сценарий полной и частичной отмены заказа + возврат."""

from __future__ import annotations

from uuid import uuid4

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from delivery_bot.dialog.keyboards import main_menu_keyboard, operator_offer_keyboard
from delivery_bot.dialog.manager import DialogResponse
from delivery_bot.dialog.session import DialogSession
from delivery_bot.dialog.states import DialogState
from delivery_bot.integrations.oms.cache import OrderStatusCache
from delivery_bot.integrations.oms.cancel_schemas import CANCEL_REASONS
from delivery_bot.integrations.oms.client import OmsClient, OmsError
from delivery_bot.integrations.oms.schemas import OrderDTO, OrderItemDTO
from delivery_bot.logging_setup import get_logger
from delivery_bot.services.order_policy import can_cancel
from delivery_bot.services.status_formatter import status_badge

logger = get_logger(__name__)

_REASON_OTHER = "other"


def _cancel_menu_keyboard(*, partial_available: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="🚫 Отменить весь заказ",
                callback_data="cancel:full",
            )
        ]
    ]
    if partial_available:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✂️ Убрать позиции",
                    callback_data="cancel:partial",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="❌ Назад в меню", callback_data="cancel:abort")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _reasons_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=label,
                callback_data=f"cancel:reason:{code}",
            )
        ]
        for code, label in CANCEL_REASONS
    ]
    rows.append(
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel:abort")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _comment_keyboard(*, allow_skip: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if allow_skip:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Пропустить комментарий",
                    callback_data="cancel:comment_skip",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel:abort")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data="cancel:confirm",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="cancel:abort",
                )
            ],
        ]
    )


def _items_keyboard(
    items: list[OrderItemDTO],
    selected: set[int],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in items:
        if item.id is None:
            continue
        mark = "✅ " if item.id in selected else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark}{item.name} ×{item.quantity} ({item.price} ₽)",
                    callback_data=f"cancel:item:{item.id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="➡️ Далее",
                callback_data="cancel:items_done",
            )
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel:abort")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


class OrderCancelService:
    """Диалог полной/частичной отмены с возвратом."""

    def __init__(self, oms: OmsClient, cache: OrderStatusCache) -> None:
        self._oms = oms
        self._cache = cache

    async def start(self, session: DialogSession) -> DialogResponse:
        order_id = session.context.get("verified_order_id")
        if not order_id:
            session.state = DialogState.AWAITING_ORDER_ID
            session.context["after_verify"] = "cancel"
            return DialogResponse(
                text=(
                    "Чтобы отменить заказ, сначала подтвердим его: "
                    "пришлите номер (например <code>ORD-1006</code>), "
                    "затем last4 телефона."
                ),
            )

        order = await self._load_order(session, str(order_id))
        if order is None:
            return DialogResponse(
                text="Не удалось загрузить заказ. Откройте «Статус» и подтвердите снова.",
                reply_markup=main_menu_keyboard(),
            )

        self._clear_pending(session)
        if not can_cancel(order.status):
            session.state = DialogState.MAIN_MENU
            return DialogResponse(
                text=(
                    f"Заказ <b>{order.id}</b> — {status_badge(order.status)}\n\n"
                    "Этот заказ уже нельзя отменить — он передан курьеру "
                    "или дальше по процессу.\n"
                    "Нажмите «Связаться с оператором», если нужна помощь."
                ),
                reply_markup=operator_offer_keyboard(active_order_id=order.id),
            )

        session.state = DialogState.CANCEL_MENU
        partial_ok = len(order.items) > 1
        return DialogResponse(
            text=(
                f"Заказ <b>{order.id}</b> — {status_badge(order.status)}\n"
                f"Сумма: {order.total_amount} ₽\n"
                f"Позиций: {len(order.items)}\n\n"
                "Что сделать?"
            ),
            reply_markup=_cancel_menu_keyboard(partial_available=partial_ok),
        )

    async def handle_callback(
        self, session: DialogSession, data: str
    ) -> DialogResponse:
        if data == "cancel:abort":
            self._clear_pending(session)
            session.state = DialogState.MAIN_MENU
            return DialogResponse(
                text="Отмена заказа прервана.",
                reply_markup=main_menu_keyboard(
                    active_order_id=session.context.get("verified_order_id")
                ),
            )

        if data == "cancel:full":
            return await self._start_full(session)
        if data == "cancel:partial":
            return await self._start_partial(session)
        if data.startswith("cancel:reason:"):
            return await self._on_reason(session, data.split(":", 2)[-1])
        if data == "cancel:comment_skip":
            return await self._on_comment(session, "")
        if data.startswith("cancel:item:"):
            item_id = int(data.split(":")[-1])
            return await self._toggle_item(session, item_id)
        if data == "cancel:items_done":
            return await self._items_done(session)
        if data == "cancel:confirm":
            return await self._confirm(session)
        return DialogResponse(text="Неизвестное действие.")

    async def handle_input(
        self, session: DialogSession, text: str
    ) -> DialogResponse:
        if session.state == DialogState.CANCEL_AWAITING_COMMENT:
            return await self._on_comment(session, text)
        return await self.start(session)

    async def _start_full(self, session: DialogSession) -> DialogResponse:
        session.context["cancel_mode"] = "full"
        session.context.pop("cancel_item_ids", None)
        session.state = DialogState.CANCEL_AWAITING_REASON
        return DialogResponse(
            text="Выберите причину полной отмены:",
            reply_markup=_reasons_keyboard(),
        )

    async def _start_partial(self, session: DialogSession) -> DialogResponse:
        order_id = session.context.get("verified_order_id")
        order = await self._load_order(session, str(order_id))
        if order is None or len(order.items) < 2:
            return DialogResponse(
                text="Частичная отмена доступна только для заказов с несколькими позициями.",
                reply_markup=_cancel_menu_keyboard(partial_available=False),
            )
        session.context["cancel_mode"] = "partial"
        session.context["cancel_item_ids"] = []
        session.state = DialogState.CANCEL_SELECT_ITEMS
        return DialogResponse(
            text=(
                "Отметьте позиции, которые нужно убрать "
                "(нажмите ещё раз, чтобы снять отметку).\n"
                "Если отметите все — будет полная отмена."
            ),
            reply_markup=_items_keyboard(order.items, set()),
        )

    async def _toggle_item(
        self, session: DialogSession, item_id: int
    ) -> DialogResponse:
        order = await self._load_order(
            session, str(session.context.get("verified_order_id"))
        )
        if order is None:
            return DialogResponse(
                text="Заказ не найден.",
                reply_markup=main_menu_keyboard(),
            )
        selected = set(int(x) for x in session.context.get("cancel_item_ids") or [])
        if item_id in selected:
            selected.remove(item_id)
        else:
            selected.add(item_id)
        session.context["cancel_item_ids"] = list(selected)
        session.state = DialogState.CANCEL_SELECT_ITEMS
        return DialogResponse(
            text=(
                f"Выбрано позиций: {len(selected)}.\n"
                "Отметьте ещё или нажмите «Далее»."
            ),
            reply_markup=_items_keyboard(order.items, selected),
        )

    async def _items_done(self, session: DialogSession) -> DialogResponse:
        selected = list(session.context.get("cancel_item_ids") or [])
        if not selected:
            order = await self._load_order(
                session, str(session.context.get("verified_order_id"))
            )
            return DialogResponse(
                text="Выберите хотя бы одну позицию.",
                reply_markup=_items_keyboard(
                    order.items if order else [], set()
                ),
            )
        session.state = DialogState.CANCEL_AWAITING_REASON
        return DialogResponse(
            text="Выберите причину частичной отмены:",
            reply_markup=_reasons_keyboard(),
        )

    async def _on_reason(
        self, session: DialogSession, reason_code: str
    ) -> DialogResponse:
        known = {c for c, _ in CANCEL_REASONS}
        if reason_code not in known:
            return DialogResponse(
                text="Неизвестная причина. Выберите из списка.",
                reply_markup=_reasons_keyboard(),
            )
        session.context["cancel_reason"] = reason_code
        session.context["cancel_comment"] = ""
        session.state = DialogState.CANCEL_AWAITING_COMMENT
        allow_skip = reason_code != _REASON_OTHER
        prompt = (
            "Опишите причину одним сообщением:"
            if reason_code == _REASON_OTHER
            else "Можете добавить комментарий или пропустить:"
        )
        return DialogResponse(
            text=prompt,
            reply_markup=_comment_keyboard(allow_skip=allow_skip),
        )

    async def _on_comment(
        self, session: DialogSession, text: str
    ) -> DialogResponse:
        reason = str(session.context.get("cancel_reason") or "")
        comment = (text or "").strip()
        if reason == _REASON_OTHER and not comment:
            return DialogResponse(
                text="Для причины «Другое» нужен комментарий. Напишите его текстом.",
                reply_markup=_comment_keyboard(allow_skip=False),
            )
        session.context["cancel_comment"] = comment[:1000]
        return await self._show_confirm(session)

    async def _show_confirm(self, session: DialogSession) -> DialogResponse:
        order = await self._load_order(
            session, str(session.context.get("verified_order_id"))
        )
        if order is None:
            return DialogResponse(
                text="Заказ не найден.",
                reply_markup=main_menu_keyboard(),
            )

        reason = str(session.context.get("cancel_reason") or "")
        reason_label = dict(CANCEL_REASONS).get(reason, reason)
        comment = str(session.context.get("cancel_comment") or "")
        mode = session.context.get("cancel_mode") or "full"
        session.context["cancel_idem"] = uuid4().hex
        session.state = DialogState.CANCEL_CONFIRM

        lines = [
            f"Заказ <b>{order.id}</b>",
            f"Причина: {reason_label}",
        ]
        if comment:
            lines.append(f"Комментарий: {comment}")

        if mode == "partial":
            selected = {int(x) for x in session.context.get("cancel_item_ids") or []}
            names = [i.name for i in order.items if i.id in selected]
            lines.append(f"Убрать: {', '.join(names)}")
            lines.append("Будет оформлен пропорциональный возврат.")
        else:
            lines.append(f"Полная отмена, возврат: {order.total_amount} ₽")

        lines.append("\nПодтвердить?")
        return DialogResponse(
            text="\n".join(lines),
            reply_markup=_confirm_keyboard(),
        )

    async def _confirm(self, session: DialogSession) -> DialogResponse:
        order_id = str(session.context.get("verified_order_id"))
        reason = str(session.context.get("cancel_reason") or "")
        comment = str(session.context.get("cancel_comment") or "")
        idem = str(session.context.get("cancel_idem") or uuid4().hex)
        mode = session.context.get("cancel_mode") or "full"

        try:
            if mode == "partial":
                item_ids = [int(x) for x in session.context.get("cancel_item_ids") or []]
                result = await self._oms.partial_cancel(
                    order_id,
                    item_ids=item_ids,
                    reason_code=reason,
                    comment=comment,
                    idempotency_key=idem,
                )
            else:
                result = await self._oms.cancel_order(
                    order_id,
                    reason_code=reason,
                    comment=comment,
                    idempotency_key=idem,
                )
        except OmsError:
            return DialogResponse(
                text="Не удалось оформить отмену — сервис недоступен. Попробуйте позже.",
                reply_markup=main_menu_keyboard(active_order_id=order_id),
            )

        self._clear_pending(session)
        session.state = DialogState.MAIN_MENU

        if result.ok and result.order:
            await self._cache.set(result.order)
            active = (
                None
                if result.order.status == "cancelled"
                else result.order.id
            )
            if result.order.status == "cancelled":
                session.context.pop("verified_order_id", None)
            return DialogResponse(
                text=result.message,
                reply_markup=main_menu_keyboard(active_order_id=active),
            )

        return DialogResponse(
            text=result.message,
            reply_markup=operator_offer_keyboard(active_order_id=order_id)
            if "оператор" in result.message.lower()
            else main_menu_keyboard(active_order_id=order_id),
        )

    def _clear_pending(self, session: DialogSession) -> None:
        for key in (
            "cancel_mode",
            "cancel_reason",
            "cancel_comment",
            "cancel_item_ids",
            "cancel_idem",
        ):
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
