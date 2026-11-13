"""Сценарий изменения адреса / времени доставки."""

from __future__ import annotations

from uuid import uuid4

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from delivery_bot.dialog.keyboards import main_menu_keyboard, operator_offer_keyboard
from delivery_bot.dialog.manager import DialogResponse
from delivery_bot.dialog.session import DialogSession
from delivery_bot.dialog.states import DialogState
from delivery_bot.integrations.oms.cache import OrderStatusCache
from delivery_bot.integrations.oms.client import OmsClient, OmsError
from delivery_bot.integrations.oms.schemas import OrderDTO
from delivery_bot.logging_setup import get_logger
from delivery_bot.services.order_policy import (
    address_change_denied_reason,
    can_change_address,
    can_change_time,
)
from delivery_bot.services.status_formatter import status_badge

logger = get_logger(__name__)


def _change_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📍 Изменить адрес",
                    callback_data="change:address",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🕒 Изменить время",
                    callback_data="change:time",
                )
            ],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")],
        ]
    )


def _pay_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Оплатить доплату",
                    callback_data="change:pay_confirm",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data="change:abort",
                )
            ],
        ]
    )


def _slots_keyboard(slots: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"change:slot:{slot_id}")]
        for slot_id, label in slots
    ]
    rows.append([InlineKeyboardButton(text="❌ Отменить", callback_data="change:abort")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


class OrderChangeService:
    """Диалог изменения параметров заказа."""

    def __init__(self, oms: OmsClient, cache: OrderStatusCache) -> None:
        self._oms = oms
        self._cache = cache

    async def start(self, session: DialogSession) -> DialogResponse:
        order_id = session.context.get("verified_order_id")
        if not order_id:
            session.state = DialogState.AWAITING_ORDER_ID
            session.context["after_verify"] = "change"
            return DialogResponse(
                text=(
                    "Чтобы изменить заказ, сначала подтвердим его: "
                    "пришлите номер (например <code>ORD-1005</code>), "
                    "затем last4 телефона."
                ),
            )

        order = await self._load_order(session, str(order_id))
        if order is None:
            return DialogResponse(
                text="Не удалось загрузить заказ. Откройте «Статус» и подтвердите снова.",
                reply_markup=main_menu_keyboard(),
            )

        session.state = DialogState.CHANGE_MENU
        addr_ok = can_change_address(order.status)
        time_ok = can_change_time(order.status)
        lines = [
            f"Заказ <b>{order.id}</b> — {status_badge(order.status)}",
            f"Адрес: {order.address}",
            f"Слот: {order.delivery_slot or '—'}",
            "",
        ]
        if not addr_ok and not time_ok:
            lines.append(
                "Этот заказ уже нельзя менять.\n"
                "Нажмите «Связаться с оператором», если нужна помощь."
            )
            session.state = DialogState.MAIN_MENU
            return DialogResponse(
                text="\n".join(lines),
                reply_markup=operator_offer_keyboard(active_order_id=order.id),
            )
        if not addr_ok:
            lines.append(address_change_denied_reason(order.status))
            lines.append("Время доставки ещё можно изменить.")
        elif not time_ok:
            lines.append("Адрес ещё можно изменить. Время — уже нельзя.")
        else:
            lines.append("Что хотите изменить?")

        return DialogResponse(
            text="\n".join(lines),
            reply_markup=_change_menu_keyboard(),
        )

    async def handle_callback(self, session: DialogSession, data: str) -> DialogResponse:
        if data == "change:abort":
            session.state = DialogState.MAIN_MENU
            session.context.pop("pending_address", None)
            session.context.pop("pending_surcharge", None)
            session.context.pop("change_idem", None)
            return DialogResponse(
                text="Изменение отменено.",
                reply_markup=main_menu_keyboard(
                    active_order_id=session.context.get("verified_order_id")
                ),
            )

        if data == "change:address":
            return await self._start_address(session)
        if data == "change:time":
            return await self._start_time(session)
        if data == "change:pay_confirm":
            return await self._confirm_pay(session)
        if data.startswith("change:slot:"):
            slot_id = data.split(":", 2)[-1]
            return await self._apply_slot(session, slot_id)
        return DialogResponse(text="Неизвестное действие.")

    async def handle_input(self, session: DialogSession, text: str) -> DialogResponse:
        if session.state == DialogState.CHANGE_AWAITING_ADDRESS:
            return await self._on_address(session, text)
        return await self.start(session)

    async def _start_address(self, session: DialogSession) -> DialogResponse:
        order_id = session.context.get("verified_order_id")
        order = await self._load_order(session, str(order_id))
        if order is None:
            return DialogResponse(
                text="Заказ не найден.",
                reply_markup=main_menu_keyboard(),
            )
        if not can_change_address(order.status):
            return DialogResponse(
                text=(
                    address_change_denied_reason(order.status)
                    + "\n\nНажмите кнопку ниже, если нужна помощь оператора."
                ),
                reply_markup=operator_offer_keyboard(
                    active_order_id=order.id,
                    include_change_retry=False,
                ),
            )
        session.state = DialogState.CHANGE_AWAITING_ADDRESS
        return DialogResponse(
            text=(
                "Введите новый адрес доставки одной строкой.\n"
                "Пример: <code>Москва, ул. Арбат, 15</code>\n"
                "Для удалённых районов (Химки, Зеленоград…) будет доплата."
            ),
        )

    async def _on_address(self, session: DialogSession, text: str) -> DialogResponse:
        order_id = str(session.context.get("verified_order_id"))
        try:
            quote = await self._oms.quote_address(order_id, text)
        except OmsError:
            return DialogResponse(
                text="Сервис временно недоступен. Попробуйте позже или «оператор».",
                reply_markup=main_menu_keyboard(active_order_id=order_id),
            )

        if not quote.ok:
            session.state = DialogState.CHANGE_MENU
            return DialogResponse(
                text=(
                    quote.message + "\n\nМожете указать другой адрес или связаться с оператором."
                ),
                reply_markup=operator_offer_keyboard(
                    active_order_id=order_id,
                    include_change_retry=True,
                ),
            )

        session.context["pending_address"] = quote.normalized_address
        session.context["pending_surcharge"] = str(quote.surcharge)
        session.context["change_idem"] = uuid4().hex

        if quote.surcharge > 0:
            session.state = DialogState.CHANGE_CONFIRM_PAY
            return DialogResponse(
                text=(
                    f"{quote.message}\n\n"
                    f"Новый адрес: <b>{quote.normalized_address}</b>\n"
                    f"Доплата: <b>{quote.surcharge} ₽</b>\n\n"
                    "Подтвердите оплату доплаты."
                ),
                reply_markup=_pay_keyboard(),
            )

        # без доплаты — сразу применяем
        return await self._apply_address(session)

    async def _confirm_pay(self, session: DialogSession) -> DialogResponse:
        return await self._apply_address(session)

    async def _apply_address(self, session: DialogSession) -> DialogResponse:
        order_id = str(session.context.get("verified_order_id"))
        address = session.context.get("pending_address")
        idem = session.context.get("change_idem") or uuid4().hex
        if not address:
            session.state = DialogState.CHANGE_MENU
            return DialogResponse(
                text="Нет адреса для сохранения.",
                reply_markup=_change_menu_keyboard(),
            )
        try:
            result = await self._oms.change_address(order_id, str(address), str(idem))
        except OmsError:
            return DialogResponse(
                text="Не удалось сохранить адрес — сервис недоступен.",
                reply_markup=main_menu_keyboard(active_order_id=order_id),
            )

        session.context.pop("pending_address", None)
        session.context.pop("pending_surcharge", None)
        session.context.pop("change_idem", None)
        session.state = DialogState.MAIN_MENU

        if result.ok and result.order:
            await self._cache.set(result.order)
            return DialogResponse(
                text=result.message + f"\nТекущий адрес: {result.order.address}",
                reply_markup=main_menu_keyboard(active_order_id=result.order.id),
            )
        return DialogResponse(
            text=result.message,
            reply_markup=main_menu_keyboard(active_order_id=order_id),
        )

    async def _start_time(self, session: DialogSession) -> DialogResponse:
        order_id = session.context.get("verified_order_id")
        order = await self._load_order(session, str(order_id))
        if order is None:
            return DialogResponse(
                text="Заказ не найден.",
                reply_markup=main_menu_keyboard(),
            )
        if not can_change_time(order.status):
            return DialogResponse(
                text=(
                    "Время уже нельзя изменить — заказ передан курьеру " "или дальше по процессу."
                ),
                reply_markup=_change_menu_keyboard(),
            )
        try:
            rules = await self._oms.get_delivery_rules()
        except OmsError:
            return DialogResponse(
                text="Не удалось загрузить слоты доставки.",
                reply_markup=_change_menu_keyboard(),
            )

        session.state = DialogState.CHANGE_AWAITING_SLOT
        slots = [(s.id, s.label) for s in rules.slots]
        return DialogResponse(
            text=(
                f"Текущий слот: <b>{order.delivery_slot or '—'}</b>\n"
                f"Мин. сумма заказа (из API): {rules.min_order_amount} ₽\n\n"
                "Выберите новое время:"
            ),
            reply_markup=_slots_keyboard(slots),
        )

    async def _apply_slot(self, session: DialogSession, slot_id: str) -> DialogResponse:
        order_id = str(session.context.get("verified_order_id"))
        try:
            result = await self._oms.change_slot(order_id, slot_id)
        except OmsError:
            return DialogResponse(
                text="Не удалось изменить время — сервис недоступен.",
                reply_markup=main_menu_keyboard(active_order_id=order_id),
            )
        session.state = DialogState.MAIN_MENU
        if result.ok and result.order:
            await self._cache.set(result.order)
            return DialogResponse(
                text=result.message,
                reply_markup=main_menu_keyboard(active_order_id=result.order.id),
            )
        return DialogResponse(
            text=result.message,
            reply_markup=main_menu_keyboard(active_order_id=order_id),
        )

    async def _load_order(self, session: DialogSession, order_id: str) -> OrderDTO | None:
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
