"""Точка входа uvicorn: ``uvicorn delivery_bot.api.app:app``."""

from delivery_bot.api import create_api_app

app = create_api_app()
