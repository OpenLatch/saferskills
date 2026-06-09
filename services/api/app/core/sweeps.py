"""In-process expiry sweep for unlisted runs (I-3.5, D-UP-17).

An asyncio loop, started from the FastAPI lifespan AFTER migrations + the pool
are up, that periodically deletes expired unlisted runs via the shared
`delete_run_cascade`. Race-safe across concurrent Machines via a session-level
`pg_advisory_lock` (a held lock makes the other Machine skip the tick, not block).
Coexists with the existing unreferenced-`artifact_blobs` sweep (distinct lock).

No Redis, no cron - the lazy generic-404 on expired tokens covers the gap if no
Machine is booted to run a tick.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_scan.persistence import delete_agent_run_cascade
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.generated.agent_run import AgentRun
from app.models.scan_run import ScanRun
from app.scan.persistence import delete_run_cascade

logger = logging.getLogger(__name__)

# Distinct from the migration advisory lock (0x5AFE5C11).
_SWEEP_LOCK_KEY = 0x5AFE5C12


async def sweep_unlisted(session: AsyncSession) -> int:
    """Delete expired unlisted runs via `delete_run_cascade`. Returns rows swept.

    Guarded by `pg_try_advisory_lock(_SWEEP_LOCK_KEY)` - if another Machine holds
    it, this returns 0 immediately (no double-delete). Releases the lock before
    returning.
    """
    got = (
        await session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _SWEEP_LOCK_KEY})
    ).scalar_one()
    if not got:
        return 0
    try:
        ids = list(
            (
                await session.execute(
                    select(ScanRun.id).where(
                        ScanRun.visibility == "unlisted",
                        ScanRun.expires_at.is_not(None),
                        ScanRun.expires_at < func.now(),
                    )
                )
            )
            .scalars()
            .all()
        )
        for run_id in ids:
            await delete_run_cascade(session, run_id, allow_public=False)
        await session.commit()
        return len(ids)
    finally:
        await session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _SWEEP_LOCK_KEY})
        await session.commit()


async def sweep_ingestion_runs(session: AsyncSession, *, days: int = 90) -> int:
    """Delete `ingestion_runs` rows older than `days` (90-day retention). Returns
    rows swept. Guarded by the SAME advisory lock as `sweep_unlisted` so only one
    Machine sweeps per tick; releases it before returning.
    """
    got = (
        await session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _SWEEP_LOCK_KEY})
    ).scalar_one()
    if not got:
        return 0
    try:
        deleted = (
            await session.execute(
                text(
                    "WITH d AS (DELETE FROM ingestion_runs "
                    "WHERE started_at < now() - make_interval(days => :days) RETURNING 1) "
                    "SELECT count(*) FROM d"
                ),
                {"days": days},
            )
        ).scalar_one()
        await session.commit()
        return deleted
    finally:
        await session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _SWEEP_LOCK_KEY})
        await session.commit()


async def sweep_cli_pow(session: AsyncSession) -> int:
    """Delete `cli_pow_spent` rows past their `expires_at` (the challenge is
    invalid after expiry anyway, so the single-use ledger row is dead weight).
    Returns rows swept. Guarded by the SAME advisory lock as the other sweeps so
    only one Machine sweeps per tick; releases it before returning."""
    got = (
        await session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _SWEEP_LOCK_KEY})
    ).scalar_one()
    if not got:
        return 0
    try:
        deleted = (
            await session.execute(
                text(
                    "WITH d AS (DELETE FROM cli_pow_spent WHERE expires_at < now() "
                    "RETURNING 1) SELECT count(*) FROM d"
                )
            )
        ).scalar_one()
        await session.commit()
        return deleted
    finally:
        await session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _SWEEP_LOCK_KEY})
        await session.commit()


async def sweep_agent_runs(session: AsyncSession) -> int:
    """Delete expired unlisted Agent Reports via `delete_agent_run_cascade`
    (I-5.5, D-5.5-19). Returns rows swept. Guarded by the SAME advisory lock as the
    other sweeps so only one Machine sweeps per tick; releases it before returning."""
    got = (
        await session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _SWEEP_LOCK_KEY})
    ).scalar_one()
    if not got:
        return 0
    try:
        ids = list(
            (
                await session.execute(
                    select(AgentRun.id).where(
                        AgentRun.visibility == "unlisted",
                        AgentRun.expires_at.is_not(None),
                        AgentRun.expires_at < func.now(),
                    )
                )
            )
            .scalars()
            .all()
        )
        for run_id in ids:
            await delete_agent_run_cascade(session, run_id, allow_public=False)
        await session.commit()
        return len(ids)
    finally:
        await session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _SWEEP_LOCK_KEY})
        await session.commit()


async def sweep_agent_run_tokens(session: AsyncSession) -> int:
    """Delete `agent_run_token_spent` rows past their `expires_at` (mirrors
    `sweep_cli_pow` - the one-time submit token is invalid after expiry, so the
    single-use ledger row is dead weight). Returns rows swept. SAME advisory lock."""
    got = (
        await session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _SWEEP_LOCK_KEY})
    ).scalar_one()
    if not got:
        return 0
    try:
        deleted = (
            await session.execute(
                text(
                    "WITH d AS (DELETE FROM agent_run_token_spent WHERE expires_at < now() "
                    "RETURNING 1) SELECT count(*) FROM d"
                )
            )
        ).scalar_one()
        await session.commit()
        return deleted
    finally:
        await session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _SWEEP_LOCK_KEY})
        await session.commit()


async def _run_one_sweep(name: str, fn: Callable[[AsyncSession], Awaitable[int]]) -> int:
    """Run one sweep in its OWN session (WS-8c).

    Each sweep gets a fresh connection so a mid-transaction error in one cannot
    poison the connection the next sweep would reuse (which previously cascaded
    every sibling into the catch-all `logger.exception` traceback). A failed
    sweep logs ONE clean WARN and returns 0 - the next tick retries it."""
    try:
        async with AsyncSessionLocal() as session:
            return await fn(session)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("expiry sweep %s failed; continuing (%s)", name, type(exc).__name__)
        return 0


async def run_sweep_loop() -> None:
    """Every `settings.sweep_interval_seconds`, try the lock + sweep (unlisted runs
    + ingestion_runs retention + cli_pow). Each sweep runs in its OWN session so one
    bad sweep can't cascade the others; one bad tick never kills the task.
    Cancellation-safe."""
    interval = get_settings().sweep_interval_seconds
    logger.info("expiry sweep loop started (interval=%ss)", interval)
    try:
        while True:
            swept = await _run_one_sweep("unlisted", sweep_unlisted)
            swept_runs = await _run_one_sweep("ingestion_runs", sweep_ingestion_runs)
            swept_pow = await _run_one_sweep("cli_pow", sweep_cli_pow)
            swept_agent = await _run_one_sweep("agent_runs", sweep_agent_runs)
            swept_agent_tok = await _run_one_sweep("agent_run_tokens", sweep_agent_run_tokens)
            if swept or swept_runs or swept_pow or swept_agent or swept_agent_tok:
                logger.info(
                    "expiry sweep removed %d unlisted run(s), %d ingestion_run(s), "
                    "%d cli_pow_spent row(s), %d agent_run(s), %d agent_run_token(s)",
                    swept,
                    swept_runs,
                    swept_pow,
                    swept_agent,
                    swept_agent_tok,
                )
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("expiry sweep loop cancelled")
        raise
