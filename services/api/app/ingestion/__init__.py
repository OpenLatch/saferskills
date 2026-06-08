"""I-04 ingestion package.

The Procrastinate app singleton lives here. It is imported by:
  - app/main.py (FastAPI lifespan: starts the worker via asyncio.create_task)
  - app/ingestion/tasks.py (per-adapter cycle + periodic task registration)
  - app/ingestion/sources/*.py (each adapter registers its class in the registry)
  - app/routers/webhooks.py (POST /webhooks/github → enqueue task .defer_async)

The worker is **in-process** — it runs inside the FastAPI process via
`asyncio.create_task(procrastinate_app.run_worker_async(...))` in the lifespan
handler (D-04-03 carve-out from I-03 D-FE-34). No new Fly Machine. Same Postgres.

Procrastinate uses its own psycopg3 connection pool (PsycopgConnector), separate
from the SQLAlchemy AsyncSession layer; we hand it the same database but with the
`+asyncpg` driver suffix stripped (psycopg3 wants a plain libpq conninfo). The
procrastinate_* tables are installed at startup via the async schema manager under
advisory lock 0x5AFE5C13 — never via an Alembic migration. We never import from
`procrastinate.contrib.django.*` (Django-only).
"""

from __future__ import annotations

from procrastinate import App, PsycopgConnector

from app.core.config import coerce_ssl_to_sslmode, get_settings

_settings = get_settings()


def _libpq_conninfo(database_url: str) -> str:
    """Render `settings.database_url` as a libpq DSN psycopg3 accepts.

    Two transforms: (1) strip the SQLAlchemy async driver suffix, and (2) rename
    the asyncpg `?ssl=…` query param back to libpq's `?sslmode=…`. Skipping (2)
    is silently fatal: `_normalize_db_dsn` coerces the env DSN's `sslmode` to
    asyncpg's `ssl` for the SQLAlchemy engine, but libpq rejects `ssl`
    (`invalid URI query parameter: "ssl"`) — so every psycopg pool connection
    fails and Procrastinate's `open_async()` dies with `PoolTimeout: pool
    initialization incomplete after 30.0 sec`, degrading the ingestion worker on
    every boot.
    """
    stripped = database_url.replace("postgresql+asyncpg://", "postgresql://", 1).replace(
        "postgresql+psycopg://", "postgresql://", 1
    )
    return coerce_ssl_to_sslmode(stripped)


procrastinate_app = App(
    # `max_size` forwards to psycopg_pool.AsyncConnectionPool — set it explicitly
    # so the job-queue connector never inherits the library default and stays
    # inside the per-Machine connection budget (crash-resilience §1.4).
    connector=PsycopgConnector(
        conninfo=_libpq_conninfo(_settings.database_url),
        max_size=_settings.ingestion_queue_pool_max_size,
    ),
    import_paths=[
        "app.ingestion.tasks",
        # Phase C periodic tasks — listed so the worker registers their cron tasks.
        "app.ingestion.tasks_popularity",
        # Durable auto-scan pipeline (scan_capability_repo + auto_scan_reconcile
        # + scan_stalled_retrier) — replaces the popularity-gated deep/lite triggers.
        "app.ingestion.tasks_scan",
        "app.ingestion.tasks_archive",
        "app.ingestion.tasks_authors",
        "app.ingestion.tasks_retention",
        "app.ingestion.framework.alerts",
        "app.ingestion.sources.claudeskills_info",
        "app.ingestion.sources.clawhub",
        "app.ingestion.sources.github_skills_webhook",
        "app.ingestion.sources.github_topics",
        "app.ingestion.sources.glama",
        "app.ingestion.sources.mcp_registry",
        "app.ingestion.sources.mcp_so",
        "app.ingestion.sources.npm",
        "app.ingestion.sources.pulsemcp",
        "app.ingestion.sources.pypi",
        "app.ingestion.sources.skillhub_club",
        "app.ingestion.sources.skills_sh",
        "app.ingestion.sources.skillsmp",
        "app.ingestion.sources.smithery",
    ],
)

# Priority for the cron-scheduled periodic maintenance tasks (reconcile drainer,
# stalled-retrier, alert evaluator, archive/popularity/author/retention sweeps).
# They share `queue="periodic"` with the bulk `recompute_one_item` fan-out (one job
# per ingested item — thousands during a cold-start crawl). Procrastinate's
# `fetch_job` orders by `priority DESC, id ASC`, so without a bump these scheduled
# tasks queue *behind* the fan-out backlog and their prior run is still `todo` when
# the next cron slot fires — which makes the periodic deferrer hit the task's
# `queueing_lock` and log a (caught, benign) unique-violation on every tick. Giving
# scheduled maintenance a higher priority than bulk backfill drains it within its
# cron window, so the conflict never arises. Preserves all dedup semantics.
PERIODIC_MAINTENANCE_PRIORITY = 10

# Priority for the per-source `ingest_cycle_*` cron tasks. Like the maintenance
# tasks above, they MUST outrank the bulk auto-scan / popularity fan-out
# (`scan_capability_repo` + `recompute_one_item`, priority 0 — thousands of jobs
# during a cold-start crawl). Without a bump, Procrastinate's `fetch_job`
# (`priority DESC, id ASC`) buries each scheduled cycle inside the fan-out id-band,
# so the single in-process worker grinds the scan backlog for days and the ingest
# cycles effectively never get a slot (every source stuck `never_run`). Set just
# below the maintenance tier so the cheap coherence crons (reconcile / alerts /
# stalled-retrier) still lead, but a scheduled collection decisively beats the
# best-effort backlog. Paired with a per-source `queueing_lock` in
# `tasks._register_periodic` so an hourly/daily cron can't stack a second cycle
# behind an in-flight one (the npm-pileup / mcp_registry-zombie-stacking bug).
INGEST_CYCLE_PRIORITY = 5

# Queues the worker listens on. Per-source ingest queues + a periodic queue
# (Phase C tasks) + the durable `scan` queue (auto-scan jobs) + default.
# Aggregator queue is declared now for Phase B.
ALL_QUEUES: list[str] = [
    "ingest_github",
    "ingest_mcp_registry",
    "ingest_npm",
    "ingest_pypi",
    "ingest_aggregator",
    "scan",
    "periodic",
    "default",
]
