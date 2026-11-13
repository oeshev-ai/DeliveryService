"""Помечает legacy-БД (созданную через create_all) как актуальную для Alembic.

Запускать один раз на существующей БД, если таблицы уже есть, а
``alembic_version`` пуста / отсутствует. После stamp последующие миграции
накатываются обычным ``alembic upgrade head``.

Пример::

    DATABASE_URL=postgresql+asyncpg://... python scripts/stamp_legacy_db.py
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from delivery_bot.config import get_settings


async def main() -> int:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as conn:
        tables = await conn.scalar(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'orders'"
            )
        )
        if not tables:
            print(
                "orders table missing — use `alembic upgrade head` on a fresh DB", file=sys.stderr
            )
            await engine.dispose()
            return 1

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
                await engine.dispose()
                return 0

    await engine.dispose()

    # Синхронный CLI alembic stamp head.
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.stamp(cfg, "head")
    print("stamped alembic head for legacy schema")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
