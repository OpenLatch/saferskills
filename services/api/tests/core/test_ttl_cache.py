"""`TtlCache`: single-flight, serve-stale-while-refreshing, keep-last-good-on-failure."""

from __future__ import annotations

import asyncio

import pytest

from app.core.ttl_cache import KeyedTtlCache, TtlCache


class _Loader:
    """Counts calls. Blocks on `release` when set, raises when `error` is set."""

    def __init__(self) -> None:
        self.calls = 0
        self.value = "v1"
        self.error: Exception | None = None
        self.release: asyncio.Event | None = None

    async def __call__(self) -> str:
        self.calls += 1
        if self.release is not None:
            await self.release.wait()
        if self.error is not None:
            raise self.error
        return self.value


async def _settle() -> None:
    """Let a background refresh task run to completion."""
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_concurrent_cold_callers_share_one_load() -> None:
    cache: TtlCache[str] = TtlCache(name="t", ttl_s=60)
    loader = _Loader()
    loader.release = asyncio.Event()

    callers = [asyncio.create_task(cache.get(loader)) for _ in range(20)]
    await _settle()
    loader.release.set()

    assert await asyncio.gather(*callers) == ["v1"] * 20
    assert loader.calls == 1


@pytest.mark.asyncio
async def test_fresh_value_is_served_without_loading() -> None:
    cache: TtlCache[str] = TtlCache(name="t", ttl_s=60)
    loader = _Loader()

    await cache.get(loader)
    await cache.get(loader)

    assert loader.calls == 1


@pytest.mark.asyncio
async def test_expired_value_is_served_immediately_and_refreshed_once() -> None:
    cache: TtlCache[str] = TtlCache(name="t", ttl_s=0)
    loader = _Loader()
    await cache.get(loader)

    loader.value = "v2"
    loader.release = asyncio.Event()
    # The refresh is blocked, yet every caller returns the old value at once.
    assert await asyncio.gather(*[cache.get(loader) for _ in range(10)]) == ["v1"] * 10
    await _settle()
    assert loader.calls == 2

    loader.release.set()
    await _settle()
    loader.release = None
    assert await cache.get(loader) == "v2"


@pytest.mark.asyncio
async def test_failed_refresh_keeps_last_good_value_and_backs_off() -> None:
    cache: TtlCache[str] = TtlCache(name="t", ttl_s=0, retry_after_s=60)
    loader = _Loader()
    await cache.get(loader)

    loader.error = RuntimeError("statement timeout")
    assert await cache.get(loader) == "v1"
    await _settle()
    assert loader.calls == 2

    # Inside the backoff window: still the old value, and no new load.
    assert await cache.get(loader) == "v1"
    await _settle()
    assert loader.calls == 2


@pytest.mark.asyncio
async def test_cold_failure_raises_then_backs_off_without_reloading() -> None:
    cache: TtlCache[str] = TtlCache(name="t", ttl_s=60, retry_after_s=60)
    loader = _Loader()
    loader.error = RuntimeError("statement timeout")

    with pytest.raises(RuntimeError):
        await cache.get(loader)
    with pytest.raises(RuntimeError):
        await cache.get(loader)

    assert loader.calls == 1


@pytest.mark.asyncio
async def test_cold_failure_retries_after_the_backoff() -> None:
    cache: TtlCache[str] = TtlCache(name="t", ttl_s=60, retry_after_s=0)
    loader = _Loader()
    loader.error = RuntimeError("statement timeout")

    with pytest.raises(RuntimeError):
        await cache.get(loader)

    loader.error = None
    assert await cache.get(loader) == "v1"
    assert loader.calls == 2


@pytest.mark.asyncio
async def test_cancelled_caller_does_not_cancel_the_shared_load() -> None:
    cache: TtlCache[str] = TtlCache(name="t", ttl_s=60)
    loader = _Loader()
    loader.release = asyncio.Event()

    leaving = asyncio.create_task(cache.get(loader))
    staying = asyncio.create_task(cache.get(loader))
    await _settle()
    leaving.cancel()
    await _settle()
    loader.release.set()

    assert await staying == "v1"
    assert loader.calls == 1


@pytest.mark.asyncio
async def test_keyed_cache_loads_per_key_and_evicts_least_recently_used() -> None:
    cache: KeyedTtlCache[str] = KeyedTtlCache(name="t", ttl_s=60, max_entries=2)
    loader = _Loader()

    await cache.get("a", loader)
    await cache.get("b", loader)
    await cache.get("a", loader)  # hit; "b" is now least recently used
    assert loader.calls == 2

    await cache.get("c", loader)  # evicts "b"
    await cache.get("a", loader)
    assert loader.calls == 3

    await cache.get("b", loader)
    assert loader.calls == 4
