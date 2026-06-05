"""Procrastinate task definitions — registered dynamically from the YAML configs.

Config-first: for every `api` source whose YAML declares a `cadence_cron`, we
register a periodic task by LOOPING `load_source_configs()` — adding a new cadenced
provider is a YAML file (+ its adapter class), never a hand-written task here. The
generic cycle body resolves the adapter via the registry and runs one `run_cycle`.

The source adapter modules are imported here so ADAPTER_REGISTRY is populated
before the loop builds tasks (Procrastinate also lists them in import_paths).
"""

from __future__ import annotations

import time
from typing import Any, cast
from uuid import UUID

import httpx
import structlog
from procrastinate.retry import RetryStrategy
from sqlalchemy import func, update

from app.ingestion import procrastinate_app

# Import side-effect: register EVERY adapter class in ADAPTER_REGISTRY (the
# sources package __init__ imports all five adapter modules). Importing the
# package — not one adapter — keeps the periodic-task loop below complete.
from app.ingestion import sources as _sources  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.ingestion.config.loader import load_source_configs
from app.ingestion.framework.base_adapter import build_adapter
from app.ingestion.framework.cursor import is_source_paused
from app.ingestion.framework.exceptions import AdapterBlockedError, IngestionError
from app.ingestion.framework.failure import classify_failure
from app.ingestion.framework.registry_adapter import RegistryAdapter
from app.ingestion.framework.retry import IngestionRetry
from app.observability.events import (
    emit_ingestion_cycle_completed,
    emit_ingestion_cycle_failed,
    emit_ingestion_cycle_started,
)

logger = structlog.get_logger(__name__)


async def run_source_cycle(source_name: str, trigger: str = "scheduled") -> dict[str, Any]:
    """Generic one-cycle runner: blocklist/pause checks → adapter.run_cycle, with
    the D-04-22 PostHog cycle telemetry (started/completed/failed) wired in.

    `trigger` ∈ {scheduled, force, manual} is threaded onto the `ingestion_runs`
    record so the eagle-eye view can tell a periodic fire from an admin force-cycle
    or a hand-run `run_one_cycle`.
    """
    from app.core.config import get_settings
    from app.db.session import AsyncSessionLocal

    settings = get_settings()
    if source_name in settings.ingestion_source_blocklist:
        logger.info("ingestion.cycle_skipped", source=source_name, reason="blocklist")
        return {"skipped": "blocklist"}

    base_adapter = build_adapter(source_name)
    if not isinstance(base_adapter, RegistryAdapter):
        logger.warning("ingestion.cycle_skipped", source=source_name, reason="not_registry_adapter")
        return {"skipped": "not_registry_adapter"}
    adapter: RegistryAdapter = base_adapter
    async with AsyncSessionLocal() as session:
        if await is_source_paused(session, source_name):
            logger.info("ingestion.cycle_skipped", source=source_name, reason="paused")
            return {"skipped": "paused"}
        # Run-record write #1 (own session, committed) — placed AFTER the
        # blocklist/pause/registry gates so a no-op tick creates no noise row.
        run_id = await record_run_started(source_name, trigger)
        logger.info("ingestion.cycle_started", source=source_name)
        emit_ingestion_cycle_started(source=source_name, cadence=adapter.cadence_cron or "")
        started = time.monotonic()
        try:
            counters: dict[str, Any] = await adapter.run_cycle(session, settings)
        except AdapterBlockedError as exc:
            # Lean stack: a Cloudflare interstitial is terminal (no Playwright tier).
            # Flip the source to `blocked` so future ticks no-op, record the failure,
            # and DO NOT re-raise — re-raising would trigger a pointless retry storm
            # against the same challenge. The 15-min pager (framework/alerts.py) +
            # the eagle-eye view surface the `blocked` state + Slack alert.
            logger.warning("ingestion.cycle_blocked", source=source_name, reason="cf_challenge")
            emit_ingestion_cycle_failed(source=source_name, reason="cf_challenge")
            await _mark_source_blocked(source_name, reason="cf_challenge")
            await record_run_finished(
                run_id,
                status="failed",
                duration_ms=int((time.monotonic() - started) * 1000),
                error=exc,
            )
            return {"skipped": "blocked"}
        except (httpx.HTTPError, OSError, IngestionError) as exc:
            # EXPECTED provider/transport/operational failure (rate limit, 5xx,
            # timeout, DNS/connection error, robots disallow, oversize body, …).
            # This is an operational event, NOT a code bug — so emit ONE clean WARN
            # (source + error class + short message), never a stack trace. Record
            # the failed run, emit the bucketed telemetry, and return WITHOUT
            # re-raising: re-raising would (a) make Procrastinate log its own
            # traceback and (b) trigger a pointless fast retry against a provider
            # that won't recover in 1 min — the periodic cron is the real retry
            # cadence. Same rationale as the AdapterBlockedError branch above.
            reason = classify_failure(exc)
            logger.warning(
                "ingestion.cycle_failed",
                source=source_name,
                reason=reason,
                error_class=type(exc).__name__,
                error=str(exc)[:300],
            )
            emit_ingestion_cycle_failed(source=source_name, reason=reason)
            await record_run_finished(
                run_id,
                status="failed",
                duration_ms=int((time.monotonic() - started) * 1000),
                error=exc,
            )
            return {"skipped": "failed", "reason": reason}
        except Exception as exc:
            # UNEXPECTED (a real bug, e.g. a KeyError in normalize) — keep the full
            # traceback so it's debuggable, and re-raise so it surfaces loudly and
            # the IngestionRetry schedule applies.
            logger.exception("ingestion.cycle_failed", source=source_name)
            emit_ingestion_cycle_failed(source=source_name, reason="other")
            # Run-record write #2 (own session) BEFORE re-raise — a rolled-back
            # cycle still leaves a durable failure record.
            await record_run_finished(
                run_id,
                status="failed",
                duration_ms=int((time.monotonic() - started) * 1000),
                error=exc,
            )
            raise
    duration_ms = int((time.monotonic() - started) * 1000)
    await record_run_finished(
        run_id, status="succeeded", duration_ms=duration_ms, counters=counters
    )
    seen = max(int(counters.get("items_seen", 0)), 1)
    emit_ingestion_cycle_completed(
        source=source_name,
        items_added=int(counters.get("items_added", 0)),
        items_updated=int(counters.get("items_updated", 0)),
        duration_ms=duration_ms,
        http_304_ratio=int(counters.get("http_304_count", 0)) / seen,
    )
    logger.info("ingestion.cycle_completed", source=source_name, **counters)
    return counters


async def record_run_started(source: str, trigger: str) -> UUID | None:
    """Insert a `running` ingestion_runs row in its OWN session and commit.

    Best-effort — a run-record write must never break the cycle, so any failure
    is logged + swallowed (the cycle still runs; the dashboard just misses a row).
    """
    from app.db.session import AsyncSessionLocal
    from app.models import IngestionRun

    try:
        async with AsyncSessionLocal() as session:
            row = IngestionRun(source=source, trigger=trigger, status="running")
            session.add(row)
            await session.flush()
            run_id = row.id
            await session.commit()
            return run_id
    except Exception:
        logger.warning("ingestion.run_record_start_failed", source=source)
        return None


async def record_run_finished(
    run_id: UUID | None,
    *,
    status: str,
    duration_ms: int,
    counters: dict[str, Any] | None = None,
    error: BaseException | None = None,
) -> None:
    """Update the run row to its terminal state in its OWN session. Best-effort."""
    if run_id is None:
        return
    from app.db.session import AsyncSessionLocal
    from app.models import IngestionRun

    values: dict[str, Any] = {
        "status": status,
        "ended_at": func.now(),
        "duration_ms": duration_ms,
    }
    if counters is not None:
        values.update(
            items_seen=int(counters.get("items_seen", 0)),
            items_added=int(counters.get("items_added", 0)),
            items_updated=int(counters.get("items_updated", 0)),
            http_304_count=int(counters.get("http_304_count", 0)),
            http_5xx_count=int(counters.get("http_5xx_count", 0)),
        )
    if error is not None:
        # Bounded exception text only — never raw artifact payload (scan-trace
        # no-raw-payload invariant, security.md).
        values["error_class"] = type(error).__name__
        values["error_message"] = str(error)[:2048]
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(IngestionRun).where(IngestionRun.id == run_id).values(**values)
            )
            await session.commit()
    except Exception:
        logger.warning("ingestion.run_record_finish_failed", run_id=str(run_id))


async def _mark_source_blocked(source: str, *, reason: str) -> None:
    """Flip a source's crawler_cursors.status to `blocked` in its own session.

    Best-effort — a status write must never mask the original block (the cycle has
    already failed-record + returned by the time this runs)."""
    from app.db.session import AsyncSessionLocal
    from app.ingestion.framework.halt import set_source_status

    try:
        async with AsyncSessionLocal() as session:
            await set_source_status(session, source, status="blocked", reason=reason)
            await session.commit()
    except Exception:
        logger.warning("ingestion.mark_blocked_failed", source=source)


def _register_periodic(source_name: str, cron: str, queue: str) -> None:
    """Register a periodic Procrastinate task for one cadenced source."""

    @procrastinate_app.periodic(cron=cron)
    @procrastinate_app.task(
        name=f"ingest_cycle_{source_name}",
        queue=queue,
        retry=cast(
            RetryStrategy, IngestionRetry()
        ),  # IngestionRetry is BaseRetryStrategy; cast accepted at runtime
    )
    async def _cycle(  # pyright: ignore[reportUnusedFunction]
        timestamp: int, _src: str = source_name, trigger: str = "scheduled"
    ) -> dict[str, Any]:
        return await run_source_cycle(_src, trigger=trigger)


# Build the periodic tasks by looping the YAML configs (config-first). Both `api`
# and `scrape` sources schedule a periodic cycle (ScrapingAdapter ⊂ RegistryAdapter,
# so run_source_cycle's isinstance guard passes); `webhook` sources are dispatched
# by POST /webhooks/github, not a cron.
for _name, _cfg in load_source_configs().items():
    if _cfg.kind in ("api", "scrape") and _cfg.cadence_cron and _cfg.enabled:
        _register_periodic(_name, _cfg.cadence_cron, _cfg.queue)
