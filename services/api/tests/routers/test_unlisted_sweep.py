"""Expiry sweep for unlisted runs (I-3.5, D-UP-17 / P1-7).

Uses the SAVEPOINT `db_session` (the sweep commits internally). Covers: expired
unlisted runs are deleted via the ordered cascade; non-expired + public runs are
left; the advisory lock makes a concurrent sweep skip (no double-delete).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.sweeps import _SWEEP_LOCK_KEY, sweep_unlisted  # pyright: ignore[reportPrivateUsage]
from app.models.scan_run import ScanRun


async def _seed_run(session: AsyncSession, *, visibility: str, days: int) -> ScanRun:
    key = hashlib.sha256(f"{visibility}{days}{datetime.now(UTC).timestamp()}".encode()).hexdigest()
    run = ScanRun(
        idempotency_key=key,
        github_url=None,
        repo_aggregate_score=0,
        repo_tier="unscoped",
        kind_tally={},
        capability_count=0,
        rubric_version="abc1234",
        engine_version="def5678",
        source="submission",
        latency_ms=0,
        file_count=0,
        status="completed",
        visibility=visibility,
        source_kind="upload",
        share_token=("t" + key[:40]) if visibility == "unlisted" else None,
        content_hash_sha256="a" * 64,
        expires_at=datetime.now(UTC) + timedelta(days=days),
    )
    session.add(run)
    await session.flush()
    return run


@pytest.mark.asyncio
async def test_sweep_deletes_expired_only(db_session: AsyncSession) -> None:
    expired = await _seed_run(db_session, visibility="unlisted", days=-1)
    fresh = await _seed_run(db_session, visibility="unlisted", days=90)

    swept = await sweep_unlisted(db_session)
    assert swept >= 1

    assert await db_session.get(ScanRun, expired.id) is None
    assert await db_session.get(ScanRun, fresh.id) is not None


@pytest.mark.asyncio
async def test_sweep_ignores_public_with_past_expiry(db_session: AsyncSession) -> None:
    # Defensive: a public row (shouldn't have expires_at) is never swept — the
    # query filters visibility='unlisted'.
    pub = await _seed_run(db_session, visibility="public", days=-1)
    await sweep_unlisted(db_session)
    assert await db_session.get(ScanRun, pub.id) is not None


@pytest.mark.asyncio
async def test_sweep_skips_when_lock_held(db_session: AsyncSession) -> None:
    expired = await _seed_run(db_session, visibility="unlisted", days=-1)

    # Hold the sweep advisory lock on a separate connection → sweep must skip.
    dsn = "postgresql://postgres:dev@localhost:5432/saferskills_dev_test"
    holder: Any = await asyncpg.connect(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        dsn
    )
    try:
        got = await holder.fetchval(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            "SELECT pg_try_advisory_lock($1)", _SWEEP_LOCK_KEY
        )
        assert got is True
        swept = await sweep_unlisted(db_session)
        assert swept == 0  # lock held elsewhere → no-op
        assert await db_session.get(ScanRun, expired.id) is not None
    finally:
        await holder.execute("SELECT pg_advisory_unlock($1)", _SWEEP_LOCK_KEY)  # pyright: ignore[reportUnknownMemberType]
        await holder.close()  # pyright: ignore[reportUnknownMemberType]
