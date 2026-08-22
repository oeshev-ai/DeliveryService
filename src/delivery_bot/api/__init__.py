"""FastAPI-приложение: health и задел под админку/WebApp API."""

from fastapi import FastAPI

from delivery_bot import __version__


def create_api_app() -> FastAPI:
    """Фабрика FastAPI-приложения.

    Итерация 0: только /health и /ready.
    Далее: админка FAQ, WebApp backend, takeover.
    """
    app = FastAPI(
        title="Delivery Bot API",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Liveness probe."""
        return {"status": "ok", "service": "api", "version": __version__}

    @app.get("/ready")
    async def ready() -> dict[str, object]:
        """Readiness probe (зависимости добавятся позже)."""
        return {
            "status": "ready",
            "service": "api",
            "version": __version__,
            "checks": {"app": True},
        }

    return app


app = create_api_app()
