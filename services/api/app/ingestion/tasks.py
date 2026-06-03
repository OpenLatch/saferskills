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

import structlog
from procrastinate.retry import RetryStrategy

from app.ingestion import procrastinate_app

# Import side-effect: register EVERY adapter class in ADAPTER_REGISTRY (the
# sources package __init__ imports all five adapter modules). Importing the
# package — not one adapter — keeps the periodic-task loop below complete.
from app.ingestion import sources as _sources  # noqa: F401  # pyright: ignore[reportUnusedImport]
from app.ingestion.config.loader import load_source_configs
from app.ingestion.framework.base_adapter import build_adapter
from app.ingestion.framework.cursor import is_source_paused
from app.ingestion.framework.registry_adapter import RegistryAdapter
from app.ingestion.framework.retry import IngestionRetry
from app.observability.events import (
    emit_ingestion_cycle_completed,
    emit_ingestion_cycle_failed,
    emit_ingestion_cycle_started,
)

logger = structlog.get_logger(__name__)


async def run_source_cycle(source_name: str) -> dict[str, Any]:
    """Generic one-cycle runner: blocklist/pause checks → adapter.run_cycle, with
    the D-04-22 PostHog cycle telemetry (started/completed/failed) wired in."""
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
        logger.info("ingestion.cycle_started", source=source_name)
        emit_ingestion_cycle_started(source=source_name, cadence=adapter.cadence_cron or "")
        started = time.monotonic()
        try:
            counters: dict[str, Any] = await adapter.run_cycle(session, settings)
        except Exception:
            logger.exception("ingestion.cycle_failed", source=source_name)
            emit_ingestion_cycle_failed(source=source_name, reason="other")
            raise
    duration_ms = int((time.monotonic() - started) * 1000)
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
        timestamp: int, _src: str = source_name
    ) -> dict[str, Any]:
        return await run_source_cycle(_src)


# Build the periodic tasks by looping the YAML configs (config-first).
for _name, _cfg in load_source_configs().items():
    if _cfg.kind == "api" and _cfg.cadence_cron and _cfg.enabled:
        _register_periodic(_name, _cfg.cadence_cron, _cfg.queue)
