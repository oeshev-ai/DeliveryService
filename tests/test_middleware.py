"""Тесты извлечения user_id и ответа при contention."""

from unittest.mock import AsyncMock, patch

from aiogram.types import CallbackQuery, Chat, Message, Update, User

from delivery_bot.middleware import _CONTENTION_TEXT, _extract_user_id, _reply_contention


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


async def test_contention_callback_sends_text_once() -> None:
    """Callback с сообщением: пустой answer() и один текст в чат."""
    user = User(id=1, is_bot=False, first_name="T")
    chat = Chat(id=1, type="private")
    message = Message(message_id=1, date=0, chat=chat, from_user=user)
    callback = CallbackQuery(
        id="cb",
        from_user=user,
        chat_instance="ci",
        data="status",
        message=message,
    )
    update = Update(update_id=1, callback_query=callback)
    with (
        patch.object(CallbackQuery, "answer", AsyncMock()) as callback_answer,
        patch.object(Message, "answer", AsyncMock()) as message_answer,
    ):
        await _reply_contention(update)
    callback_answer.assert_awaited_once_with()
    message_answer.assert_awaited_once_with(_CONTENTION_TEXT)
