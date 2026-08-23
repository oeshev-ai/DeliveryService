"""Сценарий эскалации к оператору (CRM handoff)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from delivery_bot.dialog.keyboards import main_menu_keyboard
from delivery_bot.dialog.manager import DialogResponse
from delivery_bot.dialog.session import DialogSession
from delivery_bot.dialog.states import DialogState
from delivery_bot.dialog import texts
from delivery_bot.integrations.crm.client import CrmClient, CrmError
from delivery_bot.integrations.crm.schemas import (
    AddEscalationMessageRequest,
    CreateEscalationTicketRequest,
)
from delivery_bot.logging_setup import get_logger
from delivery_bot.observability.metrics import inc_escalation

logger = get_logger(__name__)


def _handoff_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Завершить диалог с оператором",
                    callback_data="escalation:close",
                )
            ],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")],
        ]
    )


def _build_transcript(session: DialogSession) -> str:
    lines: list[str] = []
    ctx = session.context
    if order_id := ctx.get("verified_order_id"):
        lines.append(f"Заказ: {order_id}")
    if reason := ctx.get("escalation_reason"):
        lines.append(f"Причина эскалации: {reason}")
    if faq_q := ctx.get("faq_last_question"):
        lines.append(f"Последний вопрос FAQ: {faq_q}")
    if last := session.last_intent:
        lines.append(f"Последний intent: {last}")
    return "\n".join(lines) if lines else "—"


class EscalationService:
    """Эскалация в mock CRM + режим operator takeover."""

    def __init__(self, crm: CrmClient) -> None:
        self._crm = crm

    async def start(self, session: DialogSession) -> DialogResponse:
        try:
            active = await self._crm.get_active_ticket(
                channel=session.channel,
                user_id=session.user_id,
            )
        except CrmError:
            return DialogResponse(
                text="Не удалось связаться с CRM. Попробуйте позже или /menu.",
                reply_markup=main_menu_keyboard(
                    active_order_id=session.context.get("verified_order_id")
                ),
            )

        if active is not None:
            session.state = DialogState.OPERATOR_HANDOFF
            session.context["escalation_ticket_id"] = active.id
            return DialogResponse(
                text=texts.OPERATOR_HANDOFF_TEXT.format(ticket_id=active.id),
                reply_markup=_handoff_keyboard(),
            )

        session.state = DialogState.ESCALATION_AWAITING_DESCRIPTION
        reason = session.context.get("escalation_reason")
        prefix = ""
        if reason and reason != "operator":
            prefix = f"Контекст: {reason}\n\n"
        return DialogResponse(
            text=texts.ESCALATION_ASK_TEXT.format(prefix=prefix),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="❌ Отмена",
                            callback_data="escalation:cancel",
                        )
                    ]
                ]
            ),
        )

    async def handle_input(
        self,
        session: DialogSession,
        text: str,
    ) -> DialogResponse:
        if session.state == DialogState.ESCALATION_AWAITING_DESCRIPTION:
            return await self._create_ticket(session, text.strip())

        if session.state == DialogState.OPERATOR_HANDOFF:
            return await self._forward_message(session, text.strip())

        return DialogResponse(
            text="",
            delegate_escalation=True,
        )

    async def handle_callback(
        self,
        session: DialogSession,
        data: str,
    ) -> DialogResponse:
        if data == "escalation:cancel":
            session.state = DialogState.MAIN_MENU
            session.context.pop("escalation_reason", None)
            return DialogResponse(
                text="Эскалация отменена. Чем ещё помочь?",
                reply_markup=main_menu_keyboard(
                    active_order_id=session.context.get("verified_order_id")
                ),
            )

        if data == "escalation:close":
            return await self._close_handoff(session)

        return DialogResponse(text="Неизвестное действие.")

    async def _create_ticket(
        self,
        session: DialogSession,
        message: str,
    ) -> DialogResponse:
        if len(message) < 3:
            return DialogResponse(
                text="Опишите проблему чуть подробнее (минимум 3 символа).",
            )

        reason = str(session.context.get("escalation_reason") or "operator")
        order_id = session.context.get("verified_order_id")
        payload = CreateEscalationTicketRequest(
            channel=session.channel,
            user_id=session.user_id,
            order_id=str(order_id) if order_id else None,
            reason=reason,
            transcript=_build_transcript(session),
            initial_message=message,
        )
        try:
            ticket = await self._crm.create_ticket(payload)
        except CrmError as exc:
            logger.warning("escalation_create_failed", error=str(exc))
            return DialogResponse(
                text="Не удалось создать заявку. Попробуйте позже.",
                reply_markup=main_menu_keyboard(
                    active_order_id=session.context.get("verified_order_id")
                ),
            )

        session.state = DialogState.OPERATOR_HANDOFF
        session.context["escalation_ticket_id"] = ticket.id
        session.context.pop("escalation_reason", None)
        logger.info(
            "escalation_created",
            ticket_id=ticket.id,
            user_id=session.user_id,
        )
        inc_escalation(reason)
        return DialogResponse(
            text=texts.OPERATOR_TICKET_CREATED.format(ticket_id=ticket.id),
            reply_markup=_handoff_keyboard(),
        )

    async def _forward_message(
        self,
        session: DialogSession,
        message: str,
    ) -> DialogResponse:
        if len(message) < 1:
            return DialogResponse(text="Напишите сообщение для оператора.")

        ticket_id = session.context.get("escalation_ticket_id")
        if not ticket_id:
            return DialogResponse(text="", delegate_escalation=True)

        try:
            await self._crm.add_message(
                int(ticket_id),
                AddEscalationMessageRequest(sender="customer", body=message),
            )
        except CrmError:
            return DialogResponse(
                text="Не удалось отправить сообщение. Попробуйте ещё раз.",
                reply_markup=_handoff_keyboard(),
            )

        return DialogResponse(
            text=texts.OPERATOR_MESSAGE_SENT,
            reply_markup=_handoff_keyboard(),
        )

    async def _close_handoff(self, session: DialogSession) -> DialogResponse:
        ticket_id = session.context.get("escalation_ticket_id")
        if ticket_id:
            try:
                await self._crm.resolve_ticket(int(ticket_id))
            except CrmError:
                pass
        session.state = DialogState.MAIN_MENU
        session.context.pop("escalation_ticket_id", None)
        session.context.pop("escalation_reason", None)
        return DialogResponse(
            text=texts.OPERATOR_HANDOFF_CLOSED,
            reply_markup=main_menu_keyboard(
                active_order_id=session.context.get("verified_order_id")
            ),
        )
