"""Dialog Manager — маршрутизация intent → ответ / смена состояния."""

from __future__ import annotations

from dataclasses import dataclass

from delivery_bot.dialog.intents import Intent, IntentMatch, IntentMatcher
from delivery_bot.dialog.keyboards import (
    consent_keyboard,
    continue_session_keyboard,
    main_menu_keyboard,
)
from delivery_bot.dialog.session import DialogSession
from delivery_bot.dialog.states import DialogState
from delivery_bot.dialog import texts
from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)

_COMING_SOON_INTENTS = {
    Intent.CHANGE,
    Intent.CANCEL,
    Intent.FAQ,
    Intent.CLAIM,
    Intent.REVIEW,
    Intent.REORDER,
}


@dataclass(slots=True)
class DialogResponse:
    """Ответ Dialog Manager для отправки в канал."""

    text: str
    reply_markup: object | None = None
    require_consent: bool = False
    # Если True — handler должен делегировать в OrderStatusService
    delegate_status: bool = False
    force_new_status: bool = False
    delegate_courier: bool = False


class DialogManager:
    """Ядро обработки диалога: согласие, меню, intent routing."""

    def __init__(self, matcher: IntentMatcher | None = None) -> None:
        self._matcher = matcher or IntentMatcher()

    @property
    def matcher(self) -> IntentMatcher:
        return self._matcher

    def handle_intent(
        self,
        session: DialogSession,
        match: IntentMatch,
        *,
        callback_data: str | None = None,
    ) -> DialogResponse:
        """Обрабатывает распознанное намерение и обновляет ``session``."""
        session.last_intent = match.intent.value
        logger.info(
            "dialog_intent",
            user_id=session.user_id,
            state=session.state,
            intent=match.intent,
            source=match.source,
            confidence=match.confidence,
        )

        if session.state == DialogState.SESSION_EXPIRED and match.intent != Intent.CONTINUE:
            if match.intent in {Intent.START, Intent.CONSENT_ACCEPT}:
                return self._handle_start_or_consent(session, match)
            return DialogResponse(
                text=texts.SESSION_EXPIRED_TEXT,
                reply_markup=continue_session_keyboard(),
            )

        if match.intent == Intent.CONTINUE:
            return self._continue_session(session)

        if match.intent == Intent.START:
            return self._handle_start(session)

        if match.intent == Intent.CONSENT_ACCEPT:
            return self._accept_consent(session)

        if match.intent == Intent.CONSENT_DECLINE:
            return self._decline_consent(session)

        if not session.consent_accepted:
            if match.intent == Intent.HELP:
                return DialogResponse(text=texts.HELP_TEXT)
            session.state = DialogState.AWAITING_CONSENT
            return DialogResponse(
                text=texts.CONSENT_TEXT,
                reply_markup=consent_keyboard(),
                require_consent=True,
            )

        if match.intent == Intent.STATUS:
            if callback_data == "menu:status_new":
                session.context.pop("verified_order_id", None)
                session.context.pop("pending_order_id", None)
                return DialogResponse(text="", delegate_status=True, force_new_status=True)
            return DialogResponse(text="", delegate_status=True)

        if match.intent == Intent.COURIER:
            return DialogResponse(text="", delegate_courier=True)

        if match.intent == Intent.HELP:
            return DialogResponse(
                text=texts.HELP_TEXT,
                reply_markup=self._menu(session),
            )

        if match.intent == Intent.MENU:
            session.state = DialogState.MAIN_MENU
            return DialogResponse(
                text=texts.MAIN_MENU_TEXT,
                reply_markup=self._menu(session),
            )

        if match.intent == Intent.OPERATOR:
            session.state = DialogState.ESCALATED
            return DialogResponse(
                text=texts.OPERATOR_STUB_TEXT,
                reply_markup=self._menu(session),
            )

        if match.intent in _COMING_SOON_INTENTS:
            session.state = DialogState.MAIN_MENU
            return DialogResponse(
                text=texts.COMING_SOON_TEXT,
                reply_markup=self._menu(session),
            )

        session.state = DialogState.MAIN_MENU
        return DialogResponse(
            text=texts.UNKNOWN_TEXT,
            reply_markup=self._menu(session),
        )

    def _menu(self, session: DialogSession):
        active = session.context.get("verified_order_id")
        return main_menu_keyboard(active_order_id=str(active) if active else None)

    def _handle_start_or_consent(
        self,
        session: DialogSession,
        match: IntentMatch,
    ) -> DialogResponse:
        if match.intent == Intent.CONSENT_ACCEPT:
            return self._accept_consent(session)
        return self._handle_start(session)

    def _handle_start(self, session: DialogSession) -> DialogResponse:
        if session.consent_accepted:
            session.state = DialogState.MAIN_MENU
            return DialogResponse(
                text=texts.WELCOME_AFTER_CONSENT,
                reply_markup=self._menu(session),
            )
        session.state = DialogState.AWAITING_CONSENT
        return DialogResponse(
            text=texts.CONSENT_TEXT,
            reply_markup=consent_keyboard(),
            require_consent=True,
        )

    def _accept_consent(self, session: DialogSession) -> DialogResponse:
        session.consent_accepted = True
        session.state = DialogState.MAIN_MENU
        return DialogResponse(
            text=texts.WELCOME_AFTER_CONSENT,
            reply_markup=self._menu(session),
        )

    def _decline_consent(self, session: DialogSession) -> DialogResponse:
        session.consent_accepted = False
        session.state = DialogState.AWAITING_CONSENT
        return DialogResponse(text=texts.CONSENT_DECLINED_TEXT)

    def _continue_session(self, session: DialogSession) -> DialogResponse:
        if not session.consent_accepted:
            session.state = DialogState.AWAITING_CONSENT
            return DialogResponse(
                text=texts.CONSENT_TEXT,
                reply_markup=consent_keyboard(),
                require_consent=True,
            )
        session.state = DialogState.MAIN_MENU
        return DialogResponse(
            text=texts.MAIN_MENU_TEXT,
            reply_markup=self._menu(session),
        )
