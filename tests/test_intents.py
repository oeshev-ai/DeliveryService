"""Тесты IntentMatcher."""

from delivery_bot.dialog.intents import Intent, IntentMatcher


def test_match_commands() -> None:
    m = IntentMatcher()
    assert m.match_command("/start").intent == Intent.START
    assert m.match_command("help").intent == Intent.HELP
    assert m.match_command("/status@mybot").intent == Intent.STATUS


def test_match_callbacks() -> None:
    m = IntentMatcher()
    assert m.match_callback("consent:accept").intent == Intent.CONSENT_ACCEPT
    assert m.match_callback("menu:cancel").intent == Intent.CANCEL
    assert m.match_callback("session:continue").intent == Intent.CONTINUE
    assert m.match_callback("unknown:x").intent == Intent.UNKNOWN


def test_match_keywords_status() -> None:
    m = IntentMatcher()
    match = m.match_text("Где мой заказ?")
    assert match.intent == Intent.STATUS
    assert match.confidence > 0.5


def test_match_keywords_cancel() -> None:
    m = IntentMatcher()
    assert m.match_text("хочу отменить заказ").intent == Intent.CANCEL


def test_match_unknown() -> None:
    m = IntentMatcher()
    assert m.match_text("абракадабра xyz").intent == Intent.UNKNOWN
