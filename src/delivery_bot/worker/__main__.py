"""Точка входа ARQ worker (обход uvloop + Python 3.12)."""

from __future__ import annotations

import asyncio

from arq.worker import run_worker

from delivery_bot.worker import WorkerSettings


def main() -> None:
    asyncio.set_event_loop(asyncio.new_event_loop())
    run_worker(WorkerSettings)


if __name__ == "__main__":
    main()
