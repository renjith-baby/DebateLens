import asyncio

import pytest

from transcribe_service.jobs.worker import WorkerPool


@pytest.mark.asyncio
async def test_pool_runs_submitted_coroutines():
    seen: list[int] = []

    async def task(i: int) -> None:
        await asyncio.sleep(0.01)
        seen.append(i)

    pool = WorkerPool(concurrency=2)
    await pool.start()
    for i in range(5):
        await pool.submit(task(i))
    await pool.drain()
    await pool.stop()

    assert sorted(seen) == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_pool_respects_concurrency_limit():
    in_flight = 0
    peak = 0

    async def slow() -> None:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1

    pool = WorkerPool(concurrency=2)
    await pool.start()
    for _ in range(6):
        await pool.submit(slow())
    await pool.drain()
    await pool.stop()

    assert peak <= 2
