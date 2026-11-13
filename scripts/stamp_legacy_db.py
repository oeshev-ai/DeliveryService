"""Помечает legacy-БД (созданную через create_all) ревизией Alembic.

Если таблицы уже есть, а ``alembic_version`` пуста, ``alembic upgrade head``
пытается создать их снова. Скрипт ставит ревизию по фактической схеме:

* нет колонки ``orders.phone_last4`` — ``48a5fd403aa1``, затем upgrade
  донакатывает эту колонку;
* колонка уже есть (create_all текущих моделей) — ``head``.

Пустая БД не штампуется: код возврата 0, схему создаёт ``alembic upgrade head``.

``alembic stamp`` выполняет ``env.py``, который вызывает ``asyncio.run``.
Поэтому stamp запускается только после того, как проверка БД уже
завершила свой event loop.

Пример::

    DATABASE_URL=postgresql+asyncpg://... python scripts/stamp_legacy_db.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from delivery_bot.config import get_settings
from delivery_bot.db.alembic_url import set_sqlalchemy_url

# Схема initial_schema, ещё без хранимой колонки orders.phone_last4.
_LEGACY_BASELINE = "48a5fd403aa1"


async def legacy_db_action(database_url: str) -> str:
    """Определяет, что делать с уже существующей БД.

    Returns:
        ``missing`` — нет таблицы orders.
        ``stamped`` — alembic_version уже заполнена.
        ``stamp:<rev>`` — таблицы есть, ревизию ``<rev>`` нужно проставить.
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

            has_last4 = await conn.scalar(
                text(
                    "SELECT COUNT(*) FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'orders' "
                    "AND column_name = 'phone_last4'"
                )
            )
        revision = "head" if has_last4 else _LEGACY_BASELINE
        return f"stamp:{revision}"
    finally:
        await engine.dispose()


def main() -> int:
    """CLI: проверка БД и ``alembic stamp`` вне event loop.

    Returns:
        0 — штамп не нужен или проставлен. Дальше вызывают ``alembic upgrade head``.
    """
    settings = get_settings()
    action = asyncio.run(legacy_db_action(settings.database_url))
    if action == "missing":
        print("orders table missing; alembic upgrade head will create the schema")
        return 0
    if action == "stamped":
        return 0

    revision = action.removeprefix("stamp:")
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    set_sqlalchemy_url(cfg, settings.database_url)
    command.stamp(cfg, revision)
    print(f"stamped alembic {revision} for legacy schema")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
