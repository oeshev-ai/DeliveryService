"""Лёгкие миграции схемы без Alembic (MVP)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)


async def apply_schema_patches(engine: AsyncEngine) -> None:
    """Добавляет новые колонки/таблицы в уже существующую БД."""
    statements = [
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ",
    ]
    async with engine.begin() as conn:
        for stmt in statements:
            await conn.execute(text(stmt))
    logger.info("schema_patches_applied", count=len(statements))
