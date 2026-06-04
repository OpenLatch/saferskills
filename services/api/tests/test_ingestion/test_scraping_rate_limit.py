"""Tests for the per-source scrape token-bucket (framework/scraping_rate_limit.py)."""

from __future__ import annotations

import time

import pytest

from app.ingestion.framework.scraping_rate_limit import (
    acquire_scrape_slot,
    reset_scrape_slots,
)


@pytest.mark.asyncio
async def test_zero_rate_is_unthrottled() -> None:
    reset_scrape_slots()
    started = time.monotonic()
    await acquire_scrape_slot("src_zero", 0)
    await acquire_scrape_slot("src_zero", 0)
    assert (time.monotonic() - started) < 0.05


@pytest.mark.asyncio
async def test_second_call_waits_min_interval() -> None:
    reset_scrape_slots()
    rate = 20.0  # 1 / 20 = 0.05s min interval
    await acquire_scrape_slot("src_throttled", rate)  # first call: no wait
    started = time.monotonic()
    await acquire_scrape_slot("src_throttled", rate)  # second: must wait ~0.05s
    elapsed = time.monotonic() - started
    assert elapsed >= 0.04, f"expected throttle ~0.05s, waited {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_distinct_sources_do_not_block_each_other() -> None:
    reset_scrape_slots()
    rate = 5.0  # 0.2s interval
    await acquire_scrape_slot("src_a", rate)
    started = time.monotonic()
    await acquire_scrape_slot("src_b", rate)  # different key → no wait
    assert (time.monotonic() - started) < 0.05
