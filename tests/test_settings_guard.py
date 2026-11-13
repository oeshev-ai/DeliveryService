"""Тесты guard'а продакшен-конфигурации."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from delivery_bot.config import Settings


def test_local_allows_development_defaults() -> None:
    """В local дефолтные секреты допустимы."""
    settings = Settings(
        app_env="local",
        api_key="dev_api_key_change_me",
        admin_basic_password="admin_change_me",
        telegram_bot_token="",
        webapp_dev_bypass=True,
    )
    assert settings.app_env == "local"


def test_production_rejects_insecure_defaults() -> None:
    """В production дефолты и bypass запрещены."""
    with pytest.raises(ValidationError, match="Insecure production configuration"):
        Settings(
            app_env="production",
            api_key="dev_api_key_change_me",
            admin_basic_password="admin_change_me",
            telegram_bot_token="",
            webapp_dev_bypass=True,
        )


def test_production_accepts_hardened_config() -> None:
    """Production с уникальными секретами и без bypass — ок."""
    settings = Settings(
        app_env="production",
        api_key="prod_api_key_unique_value",
        admin_basic_password="prod_admin_password_unique",
        telegram_bot_token="123456:AATestTokenForProductionGuard",
        webapp_dev_bypass=False,
    )
    assert settings.app_env == "production"
    assert settings.webapp_dev_bypass is False
