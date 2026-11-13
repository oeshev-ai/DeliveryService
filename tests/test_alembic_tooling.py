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
    """Ответ information_schema: orders есть, alembic_version нет."""

    async def scalar(self, statement: object, *_args: object, **_kwargs: object) -> int:
        sql = str(statement)
        if "version_num" in sql:
            return 0
        if "alembic_version" in sql:
            return 0
        if "orders" in sql:
            return 1
        raise AssertionError(sql)

    async def __aenter__(self) -> _Conn:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None


class _Engine:
    def connect(self) -> _Conn:
        return _Conn()

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
    """``alembic stamp`` сам вызывает ``asyncio.run`` — его нельзя звать из цикла."""
    import alembic.command

    module = _load_stamp()
    monkeypatch.setattr(module, "create_async_engine", lambda _url: _Engine())

    def _fake_stamp(_cfg: object, _rev: str) -> None:
        asyncio.run(asyncio.sleep(0))

    monkeypatch.setattr(alembic.command, "stamp", _fake_stamp)

    entry = module.main()
    rc = asyncio.run(entry) if asyncio.iscoroutine(entry) else entry
    assert rc == 0
