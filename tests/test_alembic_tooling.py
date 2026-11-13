"""Alembic: percent в URL и stamp вне активного event loop."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load_stamp() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "stamp_legacy_db.py"
    spec = importlib.util.spec_from_file_location("stamp_legacy_db_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Conn:
    """Ответ information_schema для сценария stamp."""

    def __init__(self, *, orders: int = 1, phone_last4: int = 0) -> None:
        self._orders = orders
        self._phone_last4 = phone_last4

    async def scalar(self, statement: object, *_args: object, **_kwargs: object) -> int:
        sql = str(statement)
        if "version_num" in sql:
            return 0
        if "alembic_version" in sql:
            return 0
        if "phone_last4" in sql:
            return self._phone_last4
        if "orders" in sql:
            return self._orders
        raise AssertionError(sql)

    async def __aenter__(self) -> _Conn:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None


class _Engine:
    def __init__(self, conn: _Conn | None = None) -> None:
        self._conn = conn or _Conn()

    def connect(self) -> _Conn:
        return self._conn

    async def dispose(self) -> None:
        return None


def test_dockerignore_excludes_secrets_venv_and_tests() -> None:
    """Контекст сборки не должен тащить секреты, venv и тесты."""
    text = Path(".dockerignore").read_text(encoding="utf-8")
    for token in (".env", ".venv", "tests"):
        assert token in text.split()


def test_percent_encoded_database_url_roundtrips() -> None:
    """Пароль с ``%40`` не должен ронять ConfigParser и должен читаться обратно."""
    from alembic.config import Config

    from delivery_bot.db.alembic_url import set_sqlalchemy_url

    cfg = Config("alembic.ini")
    url = "postgresql+asyncpg://delivery:p%40ss@127.0.0.1:5432/delivery"
    set_sqlalchemy_url(cfg, url)
    assert cfg.get_main_option("sqlalchemy.url") == url
    root = Path(__file__).resolve().parents[1]
    for rel in ("migrations/env.py", "scripts/stamp_legacy_db.py"):
        source = (root / rel).read_text(encoding="utf-8")
        assert "set_sqlalchemy_url" in source
        assert 'set_main_option("sqlalchemy.url"' not in source


def test_stamp_legacy_cli_is_not_nested_in_running_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """``alembic stamp`` сам вызывает ``asyncio.run`` — его нельзя звать из цикла.

    Без колонки ``phone_last4`` ревизия — baseline initial_schema, не head:
    следующий ``upgrade head`` донакатывает эту колонку.
    """
    import alembic.command

    module = _load_stamp()
    monkeypatch.setattr(module, "create_async_engine", lambda _url: _Engine())
    stamped: list[str] = []

    def _fake_stamp(_cfg: object, rev: str) -> None:
        stamped.append(rev)
        asyncio.run(asyncio.sleep(0))

    monkeypatch.setattr(alembic.command, "stamp", _fake_stamp)

    entry = module.main()
    rc = asyncio.run(entry) if asyncio.iscoroutine(entry) else entry
    assert rc == 0
    assert stamped == ["48a5fd403aa1"]


def test_stamp_legacy_with_phone_last4_uses_head(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_all текущих моделей уже содержит phone_last4 — stamp head."""
    import alembic.command

    module = _load_stamp()
    monkeypatch.setattr(
        module,
        "create_async_engine",
        lambda _url: _Engine(_Conn(phone_last4=1)),
    )
    stamped: list[str] = []
    monkeypatch.setattr(alembic.command, "stamp", lambda _cfg, rev: stamped.append(rev))

    assert module.main() == 0
    assert stamped == ["head"]


def test_stamp_legacy_fresh_db_skips_stamp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Пустая БД не штампуется, код возврата 0 — дальше идёт upgrade head."""
    import alembic.command

    module = _load_stamp()
    monkeypatch.setattr(
        module,
        "create_async_engine",
        lambda _url: _Engine(_Conn(orders=0)),
    )

    def _forbid_stamp(*_args: object) -> None:
        raise AssertionError("stamp")

    monkeypatch.setattr(alembic.command, "stamp", _forbid_stamp)

    assert module.main() == 0


def test_api_image_stamps_legacy_before_upgrade() -> None:
    """Контейнер api не создаёт таблицы поверх уже существующей схемы."""
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "python scripts/stamp_legacy_db.py" in compose
    assert compose.index("stamp_legacy_db.py") < compose.index("alembic upgrade head")
    assert "COPY scripts ./scripts" in dockerfile
