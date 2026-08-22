"""Обработчики команд Telegram (aiogram)."""

from aiogram import Router

from delivery_bot.handlers import help as help_handlers
from delivery_bot.handlers import start as start_handlers


def setup_routers() -> Router:
    """Собирает корневой router со всеми handlers MVP-каркаса."""
    root = Router(name="root")
    root.include_router(start_handlers.router)
    root.include_router(help_handlers.router)
    return root
