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

from app.core.config import get_settings

_settings = get_settings()


def _libpq_conninfo(database_url: str) -> str:
    """Strip the SQLAlchemy async driver suffix so psycopg3 accepts the DSN."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1).replace(
        "postgresql+psycopg://", "postgresql://", 1
    )


procrastinate_app = App(
    connector=PsycopgConnector(conninfo=_libpq_conninfo(_settings.database_url)),
    import_paths=[
        "app.ingestion.tasks",
        "app.ingestion.sources.github_skills_webhook",
        "app.ingestion.sources.github_topics",
        "app.ingestion.sources.mcp_registry",
        "app.ingestion.sources.npm",
        "app.ingestion.sources.pypi",
    ],
)

# Queues the worker listens on. Per-source ingest queues + a periodic queue
# (Phase C tasks) + default. Aggregator queue is declared now for Phase B.
ALL_QUEUES: list[str] = [
    "ingest_github",
    "ingest_mcp_registry",
    "ingest_npm",
    "ingest_pypi",
    "ingest_aggregator",
    "periodic",
    "default",
]
