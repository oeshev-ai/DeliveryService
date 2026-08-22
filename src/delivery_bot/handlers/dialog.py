"""Единый роутер диалога: команды, текст, callback → DialogManager."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from delivery_bot.dialog.intents import Intent
from delivery_bot.dialog.manager import DialogManager
from delivery_bot.dialog.session import DialogSession
from delivery_bot.logging_setup import get_logger

router = Router(name="dialog")
logger = get_logger(__name__)


@router.message(Command("start", "help", "menu", "status", "faq", "operator", "cancel"))
async def on_command(
    message: Message,
    dialog_session: DialogSession,
    dialog_manager: DialogManager,
) -> None:
    """Обрабатывает известные slash-команды через Dialog Manager."""
    text = message.text or ""
    command = text.split()[0] if text else ""
    match = dialog_manager.matcher.match_command(command)
    response = dialog_manager.handle_intent(dialog_session, match)
    await message.answer(response.text, reply_markup=response.reply_markup)


@router.message(F.text)
async def on_text(
    message: Message,
    dialog_session: DialogSession,
    dialog_manager: DialogManager,
) -> None:
    """Свободный текст → intent matching."""
    match = dialog_manager.matcher.match_text(message.text or "")
    response = dialog_manager.handle_intent(dialog_session, match)
    await message.answer(response.text, reply_markup=response.reply_markup)


@router.callback_query(F.data.startswith("consent:"))
@router.callback_query(F.data.startswith("menu:"))
@router.callback_query(F.data.startswith("session:"))
async def on_callback(
    query: CallbackQuery,
    dialog_session: DialogSession,
    dialog_manager: DialogManager,
) -> None:
    """Inline-кнопки согласия, меню и продления сессии."""
    match = dialog_manager.matcher.match_callback(query.data or "")
    response = dialog_manager.handle_intent(dialog_session, match)
    await query.answer()
    if query.message:
        await query.message.answer(response.text, reply_markup=response.reply_markup)
    elif match.intent != Intent.UNKNOWN and query.from_user:
        logger.warning("callback_without_message", user_id=query.from_user.id)
