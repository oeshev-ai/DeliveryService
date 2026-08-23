"""FastAPI-приложение: health, mock OMS, задел под админку/WebApp."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Response
from sqlalchemy import text

from delivery_bot import __version__
from delivery_bot.api.oms_routes import router as oms_router
from delivery_bot.config import get_settings
from delivery_bot.db.seed import seed_orders
from delivery_bot.db.session import (
    create_engine,
    create_session_factory,
    init_db,
    session_scope,
)
from delivery_bot.logging_setup import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Инициализация БД и сид демо-заказов."""
    settings = get_settings()
    setup_logging(settings)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        await init_db(engine)
        async with session_scope(factory) as session:
            await seed_orders(session)
        app.state.db_ready = True
        logger.info("api_db_ready")
    except Exception:
        app.state.db_ready = False
        logger.exception("api_db_init_failed")
    app.state.engine = engine
    app.state.session_factory = factory
    logger.info("api_started", env=settings.app_env)
    yield
    await engine.dispose()
    logger.info("api_stopped")


def create_api_app(*, enable_lifespan: bool = True) -> FastAPI:
    """Фабрика FastAPI-приложения.

    Args:
        enable_lifespan: False в юнит-тестах без PostgreSQL.
    """
    app = FastAPI(
        title="Delivery Bot API",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan if enable_lifespan else None,
    )
    app.include_router(oms_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "api", "version": __version__}

    @app.get("/ready")
    async def ready(response: Response) -> dict[str, object]:
        db_ok = False
        factory = getattr(app.state, "session_factory", None)
        if factory is not None:
            try:
                async with factory() as session:
                    await session.execute(text("SELECT 1"))
                db_ok = True
            except Exception:
                db_ok = False
        if not db_ok:
            response.status_code = 503
        return {
            "status": "ready" if db_ok else "not_ready",
            "service": "api",
            "version": __version__,
            "checks": {"app": True, "postgres": db_ok},
        }

    return app


app = create_api_app()
