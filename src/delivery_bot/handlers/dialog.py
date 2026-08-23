"""Единый роутер диалога: команды, текст, callback → сервисы."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from delivery_bot.dialog.intents import Intent
from delivery_bot.dialog.manager import DialogManager, DialogResponse
from delivery_bot.dialog.session import DialogSession
from delivery_bot.dialog.states import DialogState
from delivery_bot.logging_setup import get_logger
from delivery_bot.services.courier import CourierService
from delivery_bot.services.order_change import OrderChangeService
from delivery_bot.services.order_status import OrderStatusService

router = Router(name="dialog")
logger = get_logger(__name__)

_STATUS_INPUT_STATES = {
    DialogState.AWAITING_ORDER_ID,
    DialogState.AWAITING_PHONE_LAST4,
}

_CHANGE_INPUT_STATES = {
    DialogState.CHANGE_AWAITING_ADDRESS,
    DialogState.CHANGE_CONFIRM_PAY,
    DialogState.CHANGE_AWAITING_SLOT,
    DialogState.CHANGE_MENU,
}


async def _resolve_response(
    session: DialogSession,
    response: DialogResponse,
    status_service: OrderStatusService,
    courier_service: CourierService,
    change_service: OrderChangeService,
) -> DialogResponse:
    if response.delegate_status:
        if response.force_new_status:
            session.context.pop("verified_order_id", None)
            session.context.pop("pending_order_id", None)
        return await status_service.start(session)
    if response.delegate_courier:
        return await courier_service.show(session)
    if response.delegate_change:
        return await change_service.start(session)
    return response


@router.message(Command("start", "help", "menu", "status", "faq", "operator", "cancel"))
async def on_command(
    message: Message,
    dialog_session: DialogSession,
    dialog_manager: DialogManager,
    status_service: OrderStatusService,
    courier_service: CourierService,
    change_service: OrderChangeService,
) -> None:
    text = message.text or ""
    command = text.split()[0] if text else ""
    match = dialog_manager.matcher.match_command(command)
    response = dialog_manager.handle_intent(dialog_session, match)
    response = await _resolve_response(
        dialog_session,
        response,
        status_service,
        courier_service,
        change_service,
    )
    await message.answer(response.text, reply_markup=response.reply_markup)


@router.message(F.text)
async def on_text(
    message: Message,
    dialog_session: DialogSession,
    dialog_manager: DialogManager,
    status_service: OrderStatusService,
    courier_service: CourierService,
    change_service: OrderChangeService,
) -> None:
    if dialog_session.state in _STATUS_INPUT_STATES:
        response = await status_service.handle_input(
            dialog_session, message.text or ""
        )
        if (
            dialog_session.context.get("after_verify") == "change"
            and dialog_session.context.get("verified_order_id")
            and dialog_session.state
            in {DialogState.ORDER_STATUS, DialogState.MAIN_MENU, DialogState.CHANGE_MENU}
        ):
            dialog_session.context.pop("after_verify", None)
            response = await change_service.start(dialog_session)
        await message.answer(response.text, reply_markup=response.reply_markup)
        return

    if dialog_session.state == DialogState.CHANGE_AWAITING_ADDRESS:
        response = await change_service.handle_input(
            dialog_session, message.text or ""
        )
        await message.answer(response.text, reply_markup=response.reply_markup)
        return

    match = dialog_manager.matcher.match_text(message.text or "")
    response = dialog_manager.handle_intent(dialog_session, match)
    response = await _resolve_response(
        dialog_session,
        response,
        status_service,
        courier_service,
        change_service,
    )
    await message.answer(response.text, reply_markup=response.reply_markup)


@router.callback_query(F.data.startswith("order:select:"))
async def on_order_select(
    query: CallbackQuery,
    dialog_session: DialogSession,
    status_service: OrderStatusService,
) -> None:
    data = query.data or ""
    order_id = data.split(":", 2)[-1]
    response = await status_service.select_order(dialog_session, order_id)
    await query.answer()
    if query.message:
        await query.message.answer(response.text, reply_markup=response.reply_markup)


@router.callback_query(F.data.startswith("change:"))
async def on_change_callback(
    query: CallbackQuery,
    dialog_session: DialogSession,
    change_service: OrderChangeService,
) -> None:
    response = await change_service.handle_callback(
        dialog_session, query.data or ""
    )
    await query.answer()
    if query.message:
        await query.message.answer(response.text, reply_markup=response.reply_markup)


@router.callback_query(F.data.startswith("consent:"))
@router.callback_query(F.data.startswith("menu:"))
@router.callback_query(F.data.startswith("session:"))
async def on_callback(
    query: CallbackQuery,
    dialog_session: DialogSession,
    dialog_manager: DialogManager,
    status_service: OrderStatusService,
    courier_service: CourierService,
    change_service: OrderChangeService,
) -> None:
    data = query.data or ""
    match = dialog_manager.matcher.match_callback(data)
    response = dialog_manager.handle_intent(
        dialog_session, match, callback_data=data
    )
    response = await _resolve_response(
        dialog_session,
        response,
        status_service,
        courier_service,
        change_service,
    )
    await query.answer()
    if query.message:
        await query.message.answer(response.text, reply_markup=response.reply_markup)
    elif match.intent != Intent.UNKNOWN and query.from_user:
        logger.warning("callback_without_message", user_id=query.from_user.id)
