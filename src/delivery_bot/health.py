"""HTTP health/readiness для процесса бота."""

from __future__ import annotations

from typing import Final

from aiohttp import web
from redis.asyncio import Redis

from delivery_bot import __version__
from delivery_bot.logging_setup import get_logger
from delivery_bot.observability.metrics import render_metrics
from delivery_bot.redis_client import ping_redis

logger = get_logger(__name__)

REDIS_KEY: Final[web.AppKey[Redis | None]] = web.AppKey("redis")


async def health_handler(request: web.Request) -> web.Response:
    """Liveness: процесс жив."""
    return web.json_response(
        {
            "status": "ok",
            "service": "bot",
            "version": __version__,
        }
    )


async def metrics_handler(request: web.Request) -> web.Response:
    """Prometheus metrics для процесса бота."""
    body, content_type = render_metrics()
    if not body:
        return web.Response(status=404, text="metrics disabled")
    return web.Response(body=body, content_type=content_type)


async def ready_handler(request: web.Request) -> web.Response:
    """Readiness: Redis (и далее Postgres/Telegram)."""
    redis = request.app.get(REDIS_KEY)
    redis_ok = await ping_redis(redis) if redis is not None else False
    ready = redis_ok
    status = 200 if ready else 503
    return web.json_response(
        {
            "status": "ready" if ready else "not_ready",
            "service": "bot",
            "version": __version__,
            "checks": {"app": True, "redis": redis_ok},
        },
        status=status,
    )


def create_health_app(redis: Redis | None = None) -> web.Application:
    """Создаёт aiohttp-приложение с /health и /ready."""
    app = web.Application()
    app[REDIS_KEY] = redis
    app.router.add_get("/health", health_handler)
    app.router.add_get("/ready", ready_handler)
    app.router.add_get("/metrics", metrics_handler)
    return app


async def start_health_server(
    host: str,
    port: int,
    redis: Redis | None = None,
) -> web.AppRunner:
    """Запускает health-сервер и возвращает runner для последующей остановки."""
    app = create_health_app(redis=redis)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    logger.info("health_server_started", host=host, port=port)
    return runner
