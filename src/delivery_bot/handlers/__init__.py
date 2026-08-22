"""Обработчики команд Telegram (aiogram)."""

from aiogram import Router

from delivery_bot.handlers import dialog as dialog_handlers


def setup_routers() -> Router:
    """Собирает корневой router диалогового ядра."""
    root = Router(name="root")
    root.include_router(dialog_handlers.router)
    return root
