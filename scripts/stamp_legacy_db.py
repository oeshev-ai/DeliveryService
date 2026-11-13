"""Помечает legacy-БД (созданную через create_all) как актуальную для Alembic.

Запускать один раз на существующей БД, если таблицы уже есть, а
``alembic_version`` пуста / отсутствует. После stamp последующие миграции
накатываются обычным ``alembic upgrade head``.

``alembic stamp`` выполняет ``env.py``, который вызывает ``asyncio.run``.
Поэтому stamp запускается только после того, как проверка БД уже
завершила свой event loop.

Пример::

    DATABASE_URL=postgresql+asyncpg://... python scripts/stamp_legacy_db.py
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from delivery_bot.config import get_settings
from delivery_bot.db.alembic_url import set_sqlalchemy_url


async def legacy_db_action(database_url: str) -> str:
    """Определяет, что делать с уже существующей БД.

    Returns:
        ``missing`` — нет таблицы orders, нужен ``alembic upgrade head``.
        ``stamped`` — alembic_version уже заполнена.
        ``stamp`` — таблицы есть, ревизия не проставлена.
    """
    engine: AsyncEngine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            orders = await conn.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'orders'"
                )
            )
            if not orders:
                return "missing"

            has_version = await conn.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'alembic_version'"
                )
            )
            if has_version:
                current = await conn.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
                if current:
                    print(f"already stamped at {current}; nothing to do")
                    return "stamped"
        return "stamp"
    finally:
        await engine.dispose()


def main() -> int:
    """CLI: проверка БД и ``alembic stamp head`` вне event loop."""
    settings = get_settings()
    action = asyncio.run(legacy_db_action(settings.database_url))
    if action == "missing":
        print(
            "orders table missing — use `alembic upgrade head` on a fresh DB",
            file=sys.stderr,
        )
        return 1
    if action == "stamped":
        return 0

    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    set_sqlalchemy_url(cfg, settings.database_url)
    command.stamp(cfg, "head")
    print("stamped alembic head for legacy schema")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
