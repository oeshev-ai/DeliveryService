"""Команда /help — справка по доступным командам."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from delivery_bot.logging_setup import get_logger

router = Router(name="help")
logger = get_logger(__name__)

HELP_TEXT = (
    "Справка\n\n"
    "/start — начать диалог\n"
    "/help — эта справка\n\n"
    "Сценарии статуса заказа, изменения, отмены и FAQ "
    "появятся в следующих итерациях."
)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Обрабатывает /help."""
    logger.info(
        "cmd_help",
        user_id=message.from_user.id if message.from_user else None,
    )
    await message.answer(HELP_TEXT)
