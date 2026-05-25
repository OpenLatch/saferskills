"""Async timing helpers.

`async_timed` decorates an async function so callers get the elapsed
wall-clock milliseconds back alongside the result. `Stopwatch` is the
context-manager flavour for inline measurement (e.g. inside a `for`
loop where decoration is too coarse).
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from functools import wraps
from types import TracebackType
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def async_timed(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[tuple[R, float]]]:
    """Wrap an async function to return `(result, elapsed_ms)`.

    Uses `perf_counter_ns` for sub-millisecond precision; we divide by
    1e6 instead of using `time.perf_counter()` directly so a fast call
    still shows non-zero ms in Rich tables.
    """

    @wraps(fn)
    async def inner(*args: P.args, **kwargs: P.kwargs) -> tuple[R, float]:
        start = time.perf_counter_ns()
        result = await fn(*args, **kwargs)
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
        return result, elapsed_ms

    return inner


class Stopwatch:
    """Inline elapsed-time measurement.

    Usage:
        with Stopwatch() as sw:
            await do_thing()
        print(sw.elapsed_ms)
    """

    elapsed_ms: float

    def __init__(self) -> None:
        self.elapsed_ms = 0.0
        self._start: int = 0

    def __enter__(self) -> Stopwatch:
        self._start = time.perf_counter_ns()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.elapsed_ms = (time.perf_counter_ns() - self._start) / 1_000_000
