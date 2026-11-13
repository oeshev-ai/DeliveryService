"""Тесты Redis-лока сессии на пользователя."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fakeredis.aioredis import FakeRedis

from delivery_bot.dialog.session import DialogSession, RedisSessionStore
from delivery_bot.dialog.states import DialogState
from delivery_bot.middleware import CHANNEL, DialogSessionMiddleware


@pytest.mark.asyncio
async def test_parallel_updates_serialize_session_state() -> None:
    """Второй апдейт видит состояние, сохранённое первым."""
    redis = FakeRedis(decode_responses=True)
    store = RedisSessionStore(redis, session_ttl_seconds=60, consent_ttl_seconds=120)
    mw = DialogSessionMiddleware(store)
    order: list[str] = []

    async def handler_a(event: Any, data: dict[str, Any]) -> str:
        session: DialogSession = data["dialog_session"]
        await asyncio.sleep(0.05)
        session.context["step"] = "a"
        session.state = DialogState.MAIN_MENU
        order.append("a")
        return "a"

    async def handler_b(event: Any, data: dict[str, Any]) -> str:
        session: DialogSession = data["dialog_session"]
        order.append(f"b-sees-{session.context.get('step')}")
        session.context["step"] = "b"
        return "b"

    event = object()
    data_a: dict[str, Any] = {"event_from_user": type("U", (), {"id": 7})()}
    data_b: dict[str, Any] = {"event_from_user": type("U", (), {"id": 7})()}

    # Запускаем A чуть раньше, B ждёт лок и должен увидеть step=a.
    task_a = asyncio.create_task(mw(handler_a, event, data_a))
    await asyncio.sleep(0.01)
    task_b = asyncio.create_task(mw(handler_b, event, data_b))
    await asyncio.gather(task_a, task_b)

    assert order[0] == "a"
    assert order[1] == "b-sees-a"
    loaded = await store.get(CHANNEL, "7")
    assert loaded.context.get("step") == "b"
    await redis.aclose()


@pytest.mark.asyncio
async def test_release_does_not_delete_foreign_lock() -> None:
    """Протухший/чужой лок не удаляется чужим compare-and-del."""
    redis = FakeRedis(decode_responses=True)
    store = RedisSessionStore(redis)
    mw = DialogSessionMiddleware(store)
    key = mw._lock_key("42")  # noqa: SLF001
    await redis.set(key, "holder-token", px=10_000)
    await mw._release_lock("42", "other-token")  # noqa: SLF001
    assert await redis.get(key) == "holder-token"
    await mw._release_lock("42", "holder-token")  # noqa: SLF001
    assert await redis.get(key) is None
    await redis.aclose()


@pytest.mark.asyncio
async def test_contention_skips_handler() -> None:
    """Если лок не получен — handler не вызывается, событие не сохраняется."""
    redis = FakeRedis(decode_responses=True)
    store = RedisSessionStore(redis)
    mw = DialogSessionMiddleware(store)
    await redis.set(mw._lock_key("9"), "busy", px=60_000)  # noqa: SLF001

    handler = AsyncMock(return_value="ok")
    # Укорачиваем ожидание через патч констант на уровне модуля.
    import delivery_bot.middleware as mw_mod

    original_wait = mw_mod._LOCK_WAIT_SEC
    original_retry = mw_mod._LOCK_RETRY_SEC
    mw_mod._LOCK_WAIT_SEC = 0.2
    mw_mod._LOCK_RETRY_SEC = 0.05
    try:
        result = await mw(
            handler,
            object(),
            {"event_from_user": type("U", (), {"id": 9})()},
        )
    finally:
        mw_mod._LOCK_WAIT_SEC = original_wait
        mw_mod._LOCK_RETRY_SEC = original_retry

    assert result is None
    handler.assert_not_called()
    await redis.aclose()
