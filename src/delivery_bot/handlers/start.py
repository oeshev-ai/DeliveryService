"""Команда /start — приветствие и краткое описание возможностей."""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from delivery_bot.logging_setup import get_logger

router = Router(name="start")
logger = get_logger(__name__)

WELCOME_TEXT = (
    "Привет! Я бот службы доставки 🚚\n\n"
    "Пока я в режиме каркаса (итерация 0). Скоро смогу:\n"
    "• показать статус заказа\n"
    "• помочь изменить адрес или отменить заказ\n"
    "• ответить на частые вопросы\n\n"
    "Команды: /start, /help"
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Обрабатывает /start."""
    logger.info(
        "cmd_start",
        user_id=message.from_user.id if message.from_user else None,
        chat_id=message.chat.id,
    )
    await message.answer(WELCOME_TEXT)
