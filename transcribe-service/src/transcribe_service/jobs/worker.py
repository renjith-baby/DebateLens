from __future__ import annotations

import asyncio
import logging
from typing import Coroutine

logger = logging.getLogger(__name__)


class WorkerPool:
    """Bounded async worker pool: at most `concurrency` coroutines run at once."""

    def __init__(self, concurrency: int) -> None:
        self._sem = asyncio.Semaphore(concurrency)
        self._tasks: set[asyncio.Task] = set()
        self._stopped = False

    async def start(self) -> None:
        self._stopped = False

    async def submit(self, coro: Coroutine) -> None:
        if self._stopped:
            coro.close()
            raise RuntimeError("WorkerPool stopped")
        task = asyncio.create_task(self._run(coro))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, coro: Coroutine) -> None:
        async with self._sem:
            try:
                await coro
            except Exception:
                logger.exception("worker task raised")

    async def drain(self) -> None:
        if not self._tasks:
            return
        await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def stop(self) -> None:
        self._stopped = True
        await self.drain()
