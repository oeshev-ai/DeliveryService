"""HTTP health/readiness для процесса бота."""

from __future__ import annotations

from aiohttp import web

from delivery_bot import __version__
from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)


async def health_handler(request: web.Request) -> web.Response:
    """Liveness: процесс жив."""
    return web.json_response(
        {
            "status": "ok",
            "service": "bot",
            "version": __version__,
        }
    )


async def ready_handler(request: web.Request) -> web.Response:
    """Readiness: базовые зависимости (расширится в следующих итерациях)."""
    # Итерация 0: считаем ready, если приложение запущено.
    # Позже здесь появятся проверки Redis/Postgres/Telegram.
    return web.json_response(
        {
            "status": "ready",
            "service": "bot",
            "version": __version__,
            "checks": {"app": True},
        }
    )


def create_health_app() -> web.Application:
    """Создаёт aiohttp-приложение с /health и /ready."""
    app = web.Application()
    app.router.add_get("/health", health_handler)
    app.router.add_get("/ready", ready_handler)
    return app


async def start_health_server(host: str, port: int) -> web.AppRunner:
    """Запускает health-сервер и возвращает runner для последующей остановки."""
    app = create_health_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    logger.info("health_server_started", host=host, port=port)
    return runner
