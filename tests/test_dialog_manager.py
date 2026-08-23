"""Тесты DialogManager: согласие, меню, истечение сессии."""

from delivery_bot.dialog.intents import Intent, IntentMatch
from delivery_bot.dialog.manager import DialogManager
from delivery_bot.dialog.session import DialogSession
from delivery_bot.dialog.states import DialogState


def _match(intent: Intent, source: str = "keyword") -> IntentMatch:
    return IntentMatch(intent=intent, confidence=1.0, source=source)


def test_start_without_consent_shows_consent() -> None:
    mgr = DialogManager()
    session = DialogSession(channel="telegram", user_id="1")
    resp = mgr.handle_intent(session, _match(Intent.START, "command"))
    assert session.state == DialogState.AWAITING_CONSENT
    assert resp.reply_markup is not None
    assert "соглас" in resp.text.lower() or "152" in resp.text


def test_accept_consent_opens_menu() -> None:
    mgr = DialogManager()
    session = DialogSession(channel="telegram", user_id="1")
    resp = mgr.handle_intent(session, _match(Intent.CONSENT_ACCEPT, "callback"))
    assert session.consent_accepted is True
    assert session.state == DialogState.MAIN_MENU
    assert resp.reply_markup is not None


def test_status_without_consent_redirects_to_consent() -> None:
    mgr = DialogManager()
    session = DialogSession(channel="telegram", user_id="1")
    resp = mgr.handle_intent(session, _match(Intent.STATUS))
    assert session.state == DialogState.AWAITING_CONSENT
    assert resp.require_consent is True


def test_coming_soon_after_consent() -> None:
    mgr = DialogManager()
    session = DialogSession(
        channel="telegram",
        user_id="1",
        consent_accepted=True,
        state=DialogState.MAIN_MENU,
    )
    resp = mgr.handle_intent(session, _match(Intent.CLAIM))
    assert "следующ" in resp.text.lower() or "итерац" in resp.text.lower()


def test_faq_delegates_to_service() -> None:
    mgr = DialogManager()
    session = DialogSession(
        channel="telegram",
        user_id="1",
        consent_accepted=True,
        state=DialogState.MAIN_MENU,
    )
    resp = mgr.handle_intent(session, _match(Intent.FAQ))
    assert resp.delegate_faq is True


def test_cancel_delegates_to_service() -> None:
    mgr = DialogManager()
    session = DialogSession(
        channel="telegram",
        user_id="1",
        consent_accepted=True,
        state=DialogState.MAIN_MENU,
    )
    resp = mgr.handle_intent(session, _match(Intent.CANCEL))
    assert resp.delegate_cancel is True


def test_status_delegates_to_service() -> None:
    mgr = DialogManager()
    session = DialogSession(
        channel="telegram",
        user_id="1",
        consent_accepted=True,
        state=DialogState.MAIN_MENU,
    )
    resp = mgr.handle_intent(session, _match(Intent.STATUS))
    assert resp.delegate_status is True


def test_courier_delegates_to_service() -> None:
    mgr = DialogManager()
    session = DialogSession(
        channel="telegram",
        user_id="1",
        consent_accepted=True,
        state=DialogState.MAIN_MENU,
    )
    resp = mgr.handle_intent(session, _match(Intent.COURIER))
    assert resp.delegate_courier is True


def test_change_delegates_to_service() -> None:
    mgr = DialogManager()
    session = DialogSession(
        channel="telegram",
        user_id="1",
        consent_accepted=True,
        state=DialogState.MAIN_MENU,
    )
    resp = mgr.handle_intent(session, _match(Intent.CHANGE))
    assert resp.delegate_change is True


def test_session_expired_prompts_continue() -> None:
    mgr = DialogManager()
    session = DialogSession(
        channel="telegram",
        user_id="1",
        consent_accepted=True,
        state=DialogState.SESSION_EXPIRED,
    )
    resp = mgr.handle_intent(session, _match(Intent.STATUS))
    assert "сессия истекла" in resp.text.lower() or "неактивен" in resp.text.lower()


def test_continue_restores_menu() -> None:
    mgr = DialogManager()
    session = DialogSession(
        channel="telegram",
        user_id="1",
        consent_accepted=True,
        state=DialogState.SESSION_EXPIRED,
    )
    resp = mgr.handle_intent(session, _match(Intent.CONTINUE, "callback"))
    assert session.state == DialogState.MAIN_MENU
    assert resp.reply_markup is not None
