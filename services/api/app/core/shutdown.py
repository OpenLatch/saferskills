"""Bounded teardown helpers for the FastAPI lifespan shutdown.

The lifespan `finally` tears down several background tasks + connection pools on
every reload/shutdown. Any unbounded `await` there can hang the whole process —
uvicorn's "Waiting for application shutdown." never returns, so `--reload` hangs
forever mid-ingestion (the Procrastinate worker waits for an in-flight job).

These helpers make every teardown step *structurally* incapable of hanging: each
is bounded by a small timeout and, on expiry, logs a warning and abandons the
work rather than re-awaiting it. They use `asyncio.wait` (not the cancelling
`wait_for`) for tasks so the helper itself can never hang or re-cancel.

(`ASYNC109` is suppressed below: a `timeout` parameter is the whole point of a
bounded-teardown helper — the caller has a task/coroutine handle, not a context
to wrap in `asyncio.timeout`.)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from typing import Any

logger = logging.getLogger(__name__)


async def cancel_and_settle(
    task: asyncio.Task[Any] | None,
    timeout: float,  # noqa: ASYNC109 — bounded-teardown helper, not a wrappable context
    label: str,
) -> None:
    """Cancel a background task and wait at most `timeout`s for it to settle.

    Requests cancellation, then `asyncio.wait`s (never re-cancels, never raises).
    If the task ignores cancellation past the timeout it is *abandoned* — logged
    and left to the event loop's own teardown — so this helper can never itself
    hang the shutdown. A no-op on `None`.
    """
    if task is None:
        return
    task.cancel()
    done, _pending = await asyncio.wait({task}, timeout=timeout)
    if not done:
        logger.warning("shutdown: %s did not settle within %.1fs — abandoning", label, timeout)
        return
    # The task finished (or raised on cancellation) — retrieve any
    # non-CancelledError exception so it is never re-raised out of teardown.
    if not task.cancelled():
        exc = task.exception()
        if exc is not None:
            logger.warning("shutdown: %s raised on teardown: %r", label, exc)


async def bounded[T](
    coro: Awaitable[T],
    timeout: float,  # noqa: ASYNC109 — bounded-teardown helper, not a wrappable context
    label: str,
) -> T | None:
    """Await a teardown coroutine, bounded by `timeout`s; never raise.

    For the close coroutines (`close_async`, `close_pool`) that have no task
    handle to cancel. On timeout or any error, logs a warning and returns `None`
    so the lifespan `finally` always proceeds to the next step.
    """
    try:
        return await asyncio.wait_for(coro, timeout)
    except TimeoutError:
        logger.warning("shutdown: %s did not complete within %.1fs", label, timeout)
    except Exception as exc:
        logger.warning("shutdown: %s raised on teardown: %r", label, exc)
    return None
