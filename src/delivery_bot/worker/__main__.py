"""Точка входа ARQ worker (обход uvloop + Python 3.12)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast

from arq.worker import run_worker

from delivery_bot.worker import WorkerSettings

if TYPE_CHECKING:
    from arq.typing import WorkerSettingsType


def main() -> None:
    asyncio.set_event_loop(asyncio.new_event_loop())
    run_worker(cast("WorkerSettingsType", WorkerSettings))


if __name__ == "__main__":
    main()
