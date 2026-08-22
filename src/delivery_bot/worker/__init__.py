"""ARQ worker — заготовка под фоновые задачи (отзывы, refunds, CRM sync)."""

from arq import cron
from arq.connections import RedisSettings

from delivery_bot.config import get_settings
from delivery_bot.logging_setup import get_logger, setup_logging

logger = get_logger(__name__)


async def startup(ctx: dict) -> None:
    """Инициализация воркера."""
    settings = get_settings()
    setup_logging(settings)
    ctx["settings"] = settings
    logger.info("worker_started", env=settings.app_env)


async def shutdown(ctx: dict) -> None:
    """Корректное завершение воркера."""
    logger.info("worker_stopped")


async def heartbeat(ctx: dict) -> None:
    """Периодический heartbeat (заглушка итерации 0)."""
    logger.debug("worker_heartbeat")


class WorkerSettings:
    """Настройки ARQ worker (``arq delivery_bot.worker.WorkerSettings``)."""

    functions = [heartbeat]
    cron_jobs = [cron(heartbeat, minute={0, 30})]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
