"""Конфигурация приложения из переменных окружения."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Глобальные настройки сервиса.

    Значения читаются из окружения и файла ``.env`` (если он есть).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "local"
    app_name: str = "delivery-bot"
    log_level: str = "INFO"
    log_json: bool = True

    telegram_bot_token: str = Field(default="", description="Токен BotFather")
    telegram_webapp_url: str = "http://localhost:8000/ui"

    database_url: str = "postgresql+asyncpg://delivery:delivery_secret@localhost:5432/delivery"
    redis_url: str = "redis://localhost:6379/0"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_key: str = "dev_api_key_change_me"
    admin_basic_user: str = "admin"
    admin_basic_password: str = "admin_change_me"

    health_host: str = "0.0.0.0"
    health_port: int = 8081

    # Диалог / сессии
    session_ttl_seconds: int = 1800
    consent_ttl_seconds: int = 31_536_000
    verify_max_attempts: int = 5
    verify_attempt_window_seconds: int = 900
    verify_block_seconds: int = 1800

    # OMS
    oms_base_url: str = "http://localhost:8000"
    oms_timeout_seconds: float = 3.0
    status_cache_ttl_seconds: int = 90

    # WebApp
    webapp_dev_bypass: bool = True
    webapp_binding_ttl_seconds: int = 86_400
    webapp_init_data_max_age_seconds: int = 86_400

    llm_faq_enabled: bool = False
    payment_mock: bool = True
    oms_mock: bool = True

    yandex_maps_api_key: str = ""
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_mock_latency_ms: int = 80

    claim_window_days: int = 14
    review_reminder_delay_seconds: int = 3600

    metrics_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    """Возвращает кэшированный экземпляр настроек."""
    return Settings()
