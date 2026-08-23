"""FastAPI-приложение: health, mock OMS, WebApp UI/API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from delivery_bot import __version__
from delivery_bot.api.middleware import MetricsMiddleware, RequestContextMiddleware
from delivery_bot.api.crm_routes import router as crm_router
from delivery_bot.api.admin_crm_routes import router as admin_crm_router
from delivery_bot.api.admin_faq_routes import router as admin_faq_router
from delivery_bot.api.cancel_routes import router as cancel_router
from delivery_bot.api.change_routes import router as change_router
from delivery_bot.api.post_delivery_routes import router as post_delivery_router
from delivery_bot.api.faq_routes import router as faq_router
from delivery_bot.api.oms_routes import router as oms_router
from delivery_bot.api.tms_routes import router as tms_router
from delivery_bot.api.webapp_routes import router as webapp_router
from delivery_bot.config import get_settings
from delivery_bot.db.migrate import apply_schema_patches
from delivery_bot.db.seed import seed_orders
from delivery_bot.db.seed_faq import seed_faq
from delivery_bot.db.session import (
    create_engine,
    create_session_factory,
    init_db,
    session_scope,
)
from delivery_bot.integrations.llm import LlmClient, MockLlmClient
from delivery_bot.logging_setup import get_logger, setup_logging
from delivery_bot.observability.metrics import render_metrics, setup_metrics
from delivery_bot.redis_client import create_redis

logger = get_logger(__name__)


def _webapp_static_dir() -> Path:
    """Каталог статики Mini App (project/webapp/static)."""
    # src/delivery_bot/api/__init__.py → parents[3] = project root
    return Path(__file__).resolve().parents[3] / "webapp" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Инициализация БД, Redis и сид демо-заказов."""
    settings = get_settings()
    setup_logging(settings)
    setup_metrics()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    redis = create_redis(settings)
    try:
        await init_db(engine)
        await apply_schema_patches(engine)
        async with session_scope(factory) as session:
            await seed_orders(session)
            await seed_faq(session)
        app.state.db_ready = True
        logger.info("api_db_ready")
    except Exception:
        app.state.db_ready = False
        logger.exception("api_db_init_failed")
    app.state.engine = engine
    app.state.session_factory = factory
    app.state.redis = redis

    llm: LlmClient | None = None
    if settings.llm_faq_enabled:
        if settings.llm_api_key:
            llm = LlmClient(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url or "https://api.openai.com/v1",
                model=settings.llm_model,
                mock_latency_ms=settings.llm_mock_latency_ms,
            )
        else:
            llm = MockLlmClient(mock_latency_ms=settings.llm_mock_latency_ms)
            logger.info("llm_faq_using_mock", reason="no_api_key")
        await llm.start()
        logger.info(
            "llm_faq_enabled",
            model=settings.llm_model,
            mock=isinstance(llm, MockLlmClient),
        )
    app.state.llm = llm

    logger.info("api_started", env=settings.app_env)
    yield
    if llm is not None:
        await llm.aclose()
    await redis.aclose()
    await engine.dispose()
    logger.info("api_stopped")


def create_api_app(*, enable_lifespan: bool = True) -> FastAPI:
    """Фабрика FastAPI-приложения.

    Args:
        enable_lifespan: False в юнит-тестах без PostgreSQL/Redis.
    """
    app = FastAPI(
        title="Delivery Bot API",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan if enable_lifespan else None,
    )
    app.include_router(oms_router)
    app.include_router(tms_router)
    app.include_router(change_router)
    app.include_router(cancel_router)
    app.include_router(post_delivery_router)
    app.include_router(faq_router)
    app.include_router(crm_router)
    app.include_router(admin_faq_router)
    app.include_router(admin_crm_router)
    app.include_router(webapp_router)

    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestContextMiddleware)

    static_dir = _webapp_static_dir()
    if static_dir.is_dir():
        app.mount("/ui", StaticFiles(directory=str(static_dir), html=True), name="ui")
        logger.info("webapp_static_mounted", path=str(static_dir))
    else:
        logger.warning("webapp_static_missing", path=str(static_dir))

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "api", "version": __version__}

    @app.get("/ready")
    async def ready(response: Response) -> dict[str, object]:
        db_ok = False
        redis_ok = False
        factory = getattr(app.state, "session_factory", None)
        if factory is not None:
            try:
                async with factory() as session:
                    await session.execute(text("SELECT 1"))
                db_ok = True
            except Exception:
                db_ok = False
        redis = getattr(app.state, "redis", None)
        if redis is not None:
            try:
                redis_ok = bool(await redis.ping())
            except Exception:
                redis_ok = False
        ok = db_ok and redis_ok
        if not ok:
            response.status_code = 503
        return {
            "status": "ready" if ok else "not_ready",
            "service": "api",
            "version": __version__,
            "checks": {"app": True, "postgres": db_ok, "redis": redis_ok},
        }

    @app.get("/metrics")
    async def metrics() -> Response:
        body, content_type = render_metrics()
        if not body:
            return Response(status_code=404, content="metrics disabled")
        return Response(content=body, media_type=content_type)

    return app


app = create_api_app()
