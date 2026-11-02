"""Single-flight, stale-while-revalidate, in-process TTL cache.

For an expensive aggregate read by many concurrent requests. A plain
"check, compute, store" cache stampedes: every request that misses runs the query,
and because failures are not stored, a query that times out just runs again. Here:

- Concurrent callers share one load per process.
- After the TTL, callers get the old value at once while one background task
  refreshes it.
- A failed refresh keeps the last good value. With no value to serve, callers get
  the error, and no new load starts until `retry_after_s` has passed.

The loader outlives any one request, so it must open its own session rather than
capture the request's (see `app.db.session.get_session_factory`).

In-process only, per `.claude/rules/tech-stack.md`: each machine loads separately.
"""

from __future__ import annotations

import asyncio
import time
import weakref
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_instances: weakref.WeakSet[TtlCache[Any]] = weakref.WeakSet()


class TtlCache[T]:
    def __init__(self, *, name: str, ttl_s: float, retry_after_s: float = 10.0) -> None:
        self._name = name
        self._ttl_s = ttl_s
        self._retry_after_s = retry_after_s
        self._entry: tuple[float, T] | None = None
        self._task: asyncio.Task[T] | None = None
        self._last_error: Exception | None = None
        self._retry_at = 0.0
        _instances.add(self)

    async def get(self, loader: Callable[[], Awaitable[T]]) -> T:
        now = time.monotonic()
        if self._entry is not None:
            loaded_at, value = self._entry
            if now - loaded_at >= self._ttl_s and self._task is None and now >= self._retry_at:
                self._start(loader)
            return value

        if self._task is None:
            if self._last_error is not None and now < self._retry_at:
                raise self._last_error
            self._task = self._start(loader)
        # Shielded so one disconnecting client can't cancel the load the other
        # waiters share.
        return await asyncio.shield(self._task)

    def reset(self) -> None:
        self._entry = None
        self._task = None
        self._last_error = None
        self._retry_at = 0.0

    def _start(self, loader: Callable[[], Awaitable[T]]) -> asyncio.Task[T]:
        task = asyncio.create_task(self._load(loader))
        task.add_done_callback(_mark_exception_retrieved)
        self._task = task
        return task

    async def _load(self, loader: Callable[[], Awaitable[T]]) -> T:
        try:
            value = await loader()
        except Exception as exc:
            logger.warning(
                "ttl_cache.load_failed",
                cache=self._name,
                error_type=type(exc).__name__,
                serving_stale=self._entry is not None,
            )
            self._last_error = exc
            self._retry_at = time.monotonic() + self._retry_after_s
            raise
        else:
            self._entry = (time.monotonic(), value)
            self._last_error = None
            return value
        finally:
            self._task = None


def _mark_exception_retrieved(task: asyncio.Task[Any]) -> None:
    """A background refresh has no awaiter; retrieve its error so asyncio doesn't
    report it as never retrieved. `_load` has already logged it."""
    if not task.cancelled():
        task.exception()


def reset_all_caches() -> None:
    """Empty every cache. Tests use this so state can't leak between them."""
    for cache in _instances:
        cache.reset()
