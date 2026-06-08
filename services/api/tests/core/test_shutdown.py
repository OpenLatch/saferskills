"""Regression tests for the bounded-teardown helpers (`app.core.shutdown`).

These pin the safety net behind the "`--reload` hangs forever mid-ingestion" fix:
the lifespan `finally` routes every teardown step through these helpers, so each
MUST return within its timeout even when the underlying task/coroutine refuses to
stop — otherwise uvicorn's "Waiting for application shutdown." hangs forever.

No DB, no FastAPI app — pure asyncio.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.shutdown import bounded, cancel_and_settle

pytestmark = pytest.mark.asyncio


async def test_cancel_and_settle_abandons_uncancellable_task() -> None:
    """A task that swallows CancelledError is abandoned within the timeout."""

    # A `stop` flag lets the test reclaim the otherwise-uncancellable task at the
    # end — the task short-sleeps in a loop and swallows every CancelledError,
    # modelling a job stuck past the grace period.
    stop = asyncio.Event()

    async def ignores_cancellation() -> None:
        while not stop.is_set():
            try:
                await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                continue  # deliberately refuse to die

    task = asyncio.create_task(ignores_cancellation())
    await asyncio.sleep(0)  # let it reach the first await

    # Must return within ~the timeout, NOT hang forever waiting for the task.
    await asyncio.wait_for(
        cancel_and_settle(task, timeout=0.1, label="stubborn"),
        timeout=2.0,
    )

    # Abandoned, not awaited to completion — still pending after the helper returns.
    assert not task.done()

    # Reclaim the orphan via the stop flag (it ignores cancellation, so we can't
    # cancel it — the loop exits on the next iteration once `stop` is set).
    stop.set()
    await asyncio.wait_for(task, timeout=1.0)


async def test_cancel_and_settle_settles_cooperative_task() -> None:
    """A task that honours cancellation settles cleanly (and is awaited)."""

    async def cooperative() -> None:
        await asyncio.sleep(3600)

    task = asyncio.create_task(cooperative())
    await asyncio.sleep(0)

    await cancel_and_settle(task, timeout=2.0, label="cooperative")
    assert task.cancelled()


async def test_cancel_and_settle_drains_failing_task_without_raising() -> None:
    """A task that raises a non-CancelledError is drained, never re-raised."""

    async def boom() -> None:
        raise RuntimeError("teardown boom")

    task = asyncio.create_task(boom())
    await asyncio.sleep(0)

    # Does not propagate the RuntimeError out of teardown.
    await cancel_and_settle(task, timeout=2.0, label="boom")
    assert task.done()


async def test_cancel_and_settle_none_is_noop() -> None:
    await cancel_and_settle(None, timeout=1.0, label="none")


async def test_bounded_returns_within_timeout_when_coro_stalls() -> None:
    """A close-coroutine that stalls forever is bounded; helper returns None."""

    async def never_finishes() -> str:
        await asyncio.sleep(3600)
        return "done"

    result = await asyncio.wait_for(
        bounded(never_finishes(), timeout=0.1, label="stall"),
        timeout=2.0,
    )
    assert result is None


async def test_bounded_returns_value_on_success() -> None:
    async def quick() -> str:
        return "ok"

    assert await bounded(quick(), timeout=1.0, label="quick") == "ok"


async def test_bounded_swallows_exception() -> None:
    async def boom() -> str:
        raise RuntimeError("close boom")

    assert await bounded(boom(), timeout=1.0, label="boom") is None
