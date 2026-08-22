"""Тесты извлечения user_id в session middleware."""

from aiogram.types import Chat, Message, Update, User

from delivery_bot.middleware import _extract_user_id


def test_extract_user_id_from_update_message() -> None:
    user = User(id=42, is_bot=False, first_name="Test")
    chat = Chat(id=42, type="private")
    message = Message(
        message_id=1,
        date=0,
        chat=chat,
        from_user=user,
        text="/start",
    )
    update = Update(update_id=1, message=message)
    assert _extract_user_id(update, {}) == "42"


def test_extract_user_id_from_event_from_user() -> None:
    user = User(id=99, is_bot=False, first_name="X")
    assert _extract_user_id(Update(update_id=2), {"event_from_user": user}) == "99"
