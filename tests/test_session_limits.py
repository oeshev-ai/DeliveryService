"""Тесты Redis-сессий и лимитера попыток (fakeredis)."""

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis

from delivery_bot.dialog.limits import AttemptLimiter
from delivery_bot.dialog.session import RedisSessionStore
from delivery_bot.dialog.states import DialogState


@pytest_asyncio.fixture
async def redis():
    client = FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.mark.asyncio
async def test_session_save_and_load(redis) -> None:
    store = RedisSessionStore(redis, session_ttl_seconds=60, consent_ttl_seconds=120)
    session = await store.get("telegram", "42")
    assert session.state == DialogState.AWAITING_CONSENT
    session.consent_accepted = True
    session.state = DialogState.MAIN_MENU
    await store.save(session)

    loaded = await store.get("telegram", "42")
    assert loaded.consent_accepted is True
    assert loaded.state == DialogState.MAIN_MENU


@pytest.mark.asyncio
async def test_consent_survives_session_clear(redis) -> None:
    store = RedisSessionStore(redis, session_ttl_seconds=60, consent_ttl_seconds=120)
    session = await store.get("telegram", "7")
    session.consent_accepted = True
    session.state = DialogState.MAIN_MENU
    await store.save(session)
    await store.clear_session("telegram", "7")

    restored = await store.get("telegram", "7")
    assert restored.consent_accepted is True
    assert restored.state == DialogState.SESSION_EXPIRED


@pytest.mark.asyncio
async def test_attempt_limiter_blocks_after_max(redis) -> None:
    limiter = AttemptLimiter(
        redis,
        max_attempts=3,
        window_seconds=60,
        block_seconds=120,
    )
    subject = "tg:100"
    for _ in range(2):
        result = await limiter.hit("verify", subject)
        assert result.allowed is True

    result = await limiter.hit("verify", subject)
    assert result.allowed is False
    assert result.is_blocked is True

    check = await limiter.check("verify", subject)
    assert check.allowed is False


@pytest.mark.asyncio
async def test_attempt_limiter_reset(redis) -> None:
    limiter = AttemptLimiter(redis, max_attempts=2, window_seconds=60, block_seconds=60)
    await limiter.hit("verify", "u1")
    await limiter.reset("verify", "u1")
    check = await limiter.check("verify", "u1")
    assert check.allowed is True
    assert check.attempts == 0
