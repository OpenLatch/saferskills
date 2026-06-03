"""ingestion_smoke.py — offline ingestion smoke check for CI.

Runs ONE cycle of StubAdapter (no network, no Procrastinate worker) against the
live CI database, then asserts:
  1. catalog_items has at least 1 row  (upsert path works)
  2. ingestion_events has at least 1 row with applied_at IS NOT NULL  (outbox invariant)

Usage:
    DATABASE_URL=postgresql+asyncpg://... uv run python scripts/ingestion_smoke.py

Exit codes:
    0  all assertions pass
    1  assertion failure (prints which check failed + actual count)
    2  usage / import error

Does NOT use INGESTION_WORKER_ENABLED — the worker is bypassed entirely; we call
adapter.run_cycle() directly in-process so the check is fully offline and ~1s.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Require DATABASE_URL before any SQLAlchemy import so the engine builds cleanly.
if not os.environ.get("DATABASE_URL"):
    print("ERROR: DATABASE_URL must be set", file=sys.stderr)
    sys.exit(2)

# Resolve at import time (module scope) — keeps the blocking filesystem stat out
# of the async function (ruff ASYNC240).
_API_ROOT = Path(__file__).resolve().parent.parent  # services/api/


def _migrate() -> None:
    """Run `alembic upgrade head` synchronously.

    MUST run OUTSIDE the asyncio event loop: alembic's env.py calls
    `asyncio.run(run_async_migrations())` internally, which raises
    "asyncio.run() cannot be called from a running event loop" if invoked from
    inside `asyncio.run(main())`.
    """
    from alembic import command as alembic_cmd
    from alembic.config import Config as AlembicConfig

    alembic_cfg = AlembicConfig(str(_API_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(_API_ROOT / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    alembic_cmd.upgrade(alembic_cfg, "head")
    print("alembic upgrade head: OK")


async def main() -> int:
    # Build a canned StubAdapter config with 3 fake repo-JSON dicts.
    from app.core.config import get_settings
    from app.db.session import AsyncSessionLocal
    from app.ingestion.config.loader import SourceConfig
    from app.ingestion.sources.stub import StubAdapter

    fake_items = [
        {
            "full_name": "stub-org/stub-skill-a",
            "name": "stub-skill-a",
            "owner": {"login": "stub-org"},
            "html_url": "https://github.com/stub-org/stub-skill-a",
            "description": "A fake skill for CI smoke testing.",
            "license": {"spdx_id": "MIT"},
            "stargazers_count": 42,
            "pushed_at": "2025-01-01T00:00:00Z",
            "default_branch": "main",
        },
        {
            "full_name": "stub-org/stub-mcp-b",
            "name": "stub-mcp-b",
            "owner": {"login": "stub-org"},
            "html_url": "https://github.com/stub-org/stub-mcp-b",
            "description": "A fake MCP server for CI smoke testing.",
            "license": {"spdx_id": "Apache-2.0"},
            "stargazers_count": 7,
            "pushed_at": "2025-02-01T00:00:00Z",
            "default_branch": "main",
        },
        {
            "full_name": "stub-org/stub-skill-c",
            "name": "stub-skill-c",
            "owner": {"login": "stub-org"},
            "html_url": "https://github.com/stub-org/stub-skill-c",
            "description": "Another fake skill.",
            "license": None,
            "stargazers_count": 0,
            "pushed_at": "2025-03-01T00:00:00Z",
            "default_branch": "main",
        },
    ]

    config = SourceConfig(
        name="github_topics",  # reuse a known source name to pass the validator
        kind="api",
        hosts=["api.github.com"],
        discovery={"items": fake_items},
    )
    adapter = StubAdapter(config)
    settings = get_settings()

    async with AsyncSessionLocal() as session:
        counters = await adapter.run_cycle(session, settings)

    print(f"run_cycle counters: {counters}")

    # --- Assertions ---
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM catalog_items"))
        catalog_count: int = result.scalar_one()

        result2 = await session.execute(
            text("SELECT COUNT(*) FROM ingestion_events WHERE applied_at IS NOT NULL")
        )
        events_count: int = result2.scalar_one()

    print(f"catalog_items count: {catalog_count}")
    print(f"ingestion_events (applied) count: {events_count}")

    ok = True
    if catalog_count < 1:
        print(
            f"FAIL: expected catalog_items >= 1 row, got {catalog_count}",
            file=sys.stderr,
        )
        ok = False
    if events_count < 1:
        print(
            f"FAIL: expected ingestion_events (applied) >= 1 row, got {events_count}",
            file=sys.stderr,
        )
        ok = False

    if ok:
        print(f"PASS: catalog_items={catalog_count}, ingestion_events_applied={events_count}")
        return 0
    return 1


if __name__ == "__main__":
    _migrate()  # sync — before the event loop (alembic env.py uses asyncio.run)
    raise SystemExit(asyncio.run(main()))
