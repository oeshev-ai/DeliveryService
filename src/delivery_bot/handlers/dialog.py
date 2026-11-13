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
from delivery_bot.services.claim import ClaimService
from delivery_bot.services.courier import CourierService
from delivery_bot.services.escalation import EscalationService
from delivery_bot.services.faq import FaqService
from delivery_bot.services.order_cancel import OrderCancelService
from delivery_bot.services.order_change import OrderChangeService
from delivery_bot.services.order_status import OrderStatusService
from delivery_bot.services.reorder import ReorderService
from delivery_bot.services.review import ReviewService

router = Router(name="dialog")
logger = get_logger(__name__)

_STATUS_INPUT_STATES = {
    DialogState.AWAITING_ORDER_ID,
    DialogState.AWAITING_PHONE_LAST4,
}

_AFTER_VERIFY_READY = {
    DialogState.ORDER_STATUS,
    DialogState.MAIN_MENU,
    DialogState.CHANGE_MENU,
    DialogState.CANCEL_MENU,
    DialogState.CLAIM,
    DialogState.REVIEW,
    DialogState.REORDER,
}


async def _resolve_response(
    session: DialogSession,
    response: DialogResponse,
    status_service: OrderStatusService,
    courier_service: CourierService,
    change_service: OrderChangeService,
    cancel_service: OrderCancelService,
    faq_service: FaqService,
    claim_service: ClaimService,
    review_service: ReviewService,
    reorder_service: ReorderService,
    escalation_service: EscalationService,
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
    if response.delegate_cancel:
        return await cancel_service.start(session)
    if response.delegate_faq:
        return await faq_service.start(session, query=response.faq_query)
    if response.delegate_claim:
        return await claim_service.start(session)
    if response.delegate_review:
        return await review_service.start(session)
    if response.delegate_reorder:
        return await reorder_service.start(session)
    if response.delegate_escalation:
        return await escalation_service.start(session)
    return response


async def _after_verify_route(
    session: DialogSession,
    after: str,
    change_service: OrderChangeService,
    cancel_service: OrderCancelService,
    claim_service: ClaimService,
    review_service: ReviewService,
    reorder_service: ReorderService,
) -> DialogResponse:
    if after == "change":
        return await change_service.start(session)
    if after == "cancel":
        return await cancel_service.start(session)
    if after == "claim":
        return await claim_service.start(session)
    if after == "review":
        return await review_service.start(session)
    if after == "reorder":
        return await reorder_service.start(session)
    return DialogResponse(text="")


@router.message(Command("start", "help", "menu", "status", "faq", "operator", "cancel"))
async def on_command(
    message: Message,
    dialog_session: DialogSession,
    dialog_manager: DialogManager,
    status_service: OrderStatusService,
    courier_service: CourierService,
    change_service: OrderChangeService,
    cancel_service: OrderCancelService,
    faq_service: FaqService,
    claim_service: ClaimService,
    review_service: ReviewService,
    reorder_service: ReorderService,
    escalation_service: EscalationService,
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
        cancel_service,
        faq_service,
        claim_service,
        review_service,
        reorder_service,
        escalation_service,
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
    cancel_service: OrderCancelService,
    faq_service: FaqService,
    claim_service: ClaimService,
    review_service: ReviewService,
    reorder_service: ReorderService,
    escalation_service: EscalationService,
) -> None:
    text = message.text or ""
    if dialog_session.state in {
        DialogState.ESCALATION_AWAITING_DESCRIPTION,
        DialogState.OPERATOR_HANDOFF,
    }:
        if text.startswith("/menu"):
            dialog_session.state = DialogState.MAIN_MENU
            response = DialogResponse(
                text="Вернулись в меню. Заявка оператору остаётся активной.",
                reply_markup=dialog_manager._menu(dialog_session),
            )
        else:
            response = await escalation_service.handle_input(dialog_session, text)
        await message.answer(response.text, reply_markup=response.reply_markup)
        return

    if dialog_session.state in _STATUS_INPUT_STATES:
        response = await status_service.handle_input(dialog_session, message.text or "")
        after = dialog_session.context.get("after_verify")
        if (
            after in {"change", "cancel", "claim", "review", "reorder"}
            and dialog_session.context.get("verified_order_id")
            and dialog_session.state in _AFTER_VERIFY_READY
        ):
            dialog_session.context.pop("after_verify", None)
            response = await _after_verify_route(
                dialog_session,
                after,
                change_service,
                cancel_service,
                claim_service,
                review_service,
                reorder_service,
            )
        await message.answer(response.text, reply_markup=response.reply_markup)
        return

    if dialog_session.state == DialogState.CHANGE_AWAITING_ADDRESS:
        response = await change_service.handle_input(dialog_session, message.text or "")
        await message.answer(response.text, reply_markup=response.reply_markup)
        return

    if dialog_session.state == DialogState.CANCEL_AWAITING_COMMENT:
        response = await cancel_service.handle_input(dialog_session, message.text or "")
        await message.answer(response.text, reply_markup=response.reply_markup)
        return

    if dialog_session.state == DialogState.CLAIM:
        response = await claim_service.handle_input(dialog_session, message.text or "")
        await message.answer(response.text, reply_markup=response.reply_markup)
        return

    if dialog_session.state == DialogState.REVIEW:
        response = await review_service.handle_input(dialog_session, message.text or "")
        await message.answer(response.text, reply_markup=response.reply_markup)
        return

    if dialog_session.state == DialogState.FAQ:
        response = await faq_service.handle_input(dialog_session, message.text or "")
        await message.answer(response.text, reply_markup=response.reply_markup)
        return

    match = dialog_manager.matcher.match_text(message.text or "")
    response = dialog_manager.handle_intent(dialog_session, match)
    if response.delegate_faq and match.source == "keyword":
        response = DialogResponse(
            text="",
            delegate_faq=True,
            faq_query=message.text,
        )
    response = await _resolve_response(
        dialog_session,
        response,
        status_service,
        courier_service,
        change_service,
        cancel_service,
        faq_service,
        claim_service,
        review_service,
        reorder_service,
        escalation_service,
    )
    await message.answer(response.text, reply_markup=response.reply_markup)


@router.callback_query(F.data.startswith("escalation:"))
async def on_escalation_callback(
    query: CallbackQuery,
    dialog_session: DialogSession,
    escalation_service: EscalationService,
) -> None:
    response = await escalation_service.handle_callback(dialog_session, query.data or "")
    await query.answer()
    if query.message:
        await query.message.answer(response.text, reply_markup=response.reply_markup)


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
    response = await change_service.handle_callback(dialog_session, query.data or "")
    await query.answer()
    if query.message:
        await query.message.answer(response.text, reply_markup=response.reply_markup)


@router.callback_query(F.data.startswith("cancel:"))
async def on_cancel_callback(
    query: CallbackQuery,
    dialog_session: DialogSession,
    cancel_service: OrderCancelService,
) -> None:
    response = await cancel_service.handle_callback(dialog_session, query.data or "")
    await query.answer()
    if query.message:
        await query.message.answer(response.text, reply_markup=response.reply_markup)


@router.callback_query(F.data.startswith("faq:"))
async def on_faq_callback(
    query: CallbackQuery,
    dialog_session: DialogSession,
    faq_service: FaqService,
) -> None:
    response = await faq_service.handle_callback(dialog_session, query.data or "")
    await query.answer()
    if query.message:
        await query.message.answer(response.text, reply_markup=response.reply_markup)


@router.callback_query(F.data.startswith("claim:"))
async def on_claim_callback(
    query: CallbackQuery,
    dialog_session: DialogSession,
    claim_service: ClaimService,
) -> None:
    response = await claim_service.handle_callback(dialog_session, query.data or "")
    await query.answer()
    if query.message:
        await query.message.answer(response.text, reply_markup=response.reply_markup)


@router.callback_query(F.data.startswith("review:"))
async def on_review_callback(
    query: CallbackQuery,
    dialog_session: DialogSession,
    review_service: ReviewService,
) -> None:
    response = await review_service.handle_callback(dialog_session, query.data or "")
    await query.answer()
    if query.message:
        await query.message.answer(response.text, reply_markup=response.reply_markup)


@router.callback_query(F.data.startswith("reorder:"))
async def on_reorder_callback(
    query: CallbackQuery,
    dialog_session: DialogSession,
    reorder_service: ReorderService,
) -> None:
    response = await reorder_service.handle_callback(dialog_session, query.data or "")
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
    cancel_service: OrderCancelService,
    faq_service: FaqService,
    claim_service: ClaimService,
    review_service: ReviewService,
    reorder_service: ReorderService,
    escalation_service: EscalationService,
) -> None:
    data = query.data or ""
    match = dialog_manager.matcher.match_callback(data)
    response = dialog_manager.handle_intent(dialog_session, match, callback_data=data)
    response = await _resolve_response(
        dialog_session,
        response,
        status_service,
        courier_service,
        change_service,
        cancel_service,
        faq_service,
        claim_service,
        review_service,
        reorder_service,
        escalation_service,
    )
    await query.answer()
    if query.message:
        await query.message.answer(response.text, reply_markup=response.reply_markup)
    elif match.intent != Intent.UNKNOWN and query.from_user:
        logger.warning("callback_without_message", user_id=query.from_user.id)
