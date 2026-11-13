"""Тесты health-эндпоинтов."""

import pytest
from aiohttp.test_utils import TestClient, TestServer
from fakeredis.aioredis import FakeRedis
from fastapi.testclient import TestClient as FastAPITestClient

from delivery_bot.api import create_api_app
from delivery_bot.channels import (
    OutboundMessage,
    ViberAdapter,
    WebWidgetAdapter,
    WhatsAppAdapter,
)
from delivery_bot.health import create_health_app


@pytest.mark.asyncio
async def test_bot_health_ok() -> None:
    app = create_health_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "bot"


@pytest.mark.asyncio
async def test_bot_ready_without_redis_not_ready() -> None:
    app = create_health_app(redis=None)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/ready")
        assert resp.status == 503
        data = await resp.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["redis"] is False


@pytest.mark.asyncio
async def test_bot_ready_with_redis_ok() -> None:
    redis = FakeRedis(decode_responses=True)
    app = create_health_app(redis=redis)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/ready")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ready"
        assert data["checks"]["redis"] is True
    await redis.aclose()


def test_api_health_ok() -> None:
    client = FastAPITestClient(create_api_app(enable_lifespan=False))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "api"


@pytest.mark.asyncio
async def test_stub_channels_not_ready() -> None:
    stubs = [ViberAdapter(), WhatsAppAdapter(), WebWidgetAdapter()]
    for adapter in stubs:
        assert await adapter.is_ready() is False
        await adapter.send_message(OutboundMessage(chat_id="1", text="ping"))
