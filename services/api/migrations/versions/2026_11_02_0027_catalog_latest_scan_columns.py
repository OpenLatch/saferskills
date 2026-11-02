"""denormalise each catalog item's latest completed scan onto catalog_items

Revision ID: 0027_catalog_latest_scan_columns
Revises: 0026_add_crawler_alert_cooldown
Create Date: 2026-11-02

Catalog reads recomputed "latest scan" over all of `scans` on every request. These
columns hold that answer, kept current by `app/scan/persistence.py::refresh_latest_scan`
and filled for existing rows by the `latest_scan_backfill` task, not here: migrations
run on API boot, so a long one would fail the canary.

Migrations can also meet a busy database, which shapes the rest:

- The ALTER needs an exclusive lock. Queueing for it unbounded would block every read
  behind it, and failing would put the API in degraded mode, so it takes a short lock
  timeout and retries.
- Indexes are built CONCURRENTLY. An interrupted build leaves an INVALID index that
  `IF NOT EXISTS` would skip, so each one is dropped first. That also makes a re-run
  after a killed boot safe.

Reversible: `downgrade()` drops the indexes and columns.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_catalog_latest_scan_columns"
down_revision: str | None = "0026_add_crawler_alert_cooldown"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LOCK_NOT_AVAILABLE = "55P03"
_ALTER_ATTEMPTS = 20
_ALTER_PAUSE_S = 2

_ADD_COLUMNS = """
    ALTER TABLE catalog_items
        ADD COLUMN IF NOT EXISTS latest_scan_id uuid,
        ADD COLUMN IF NOT EXISTS latest_scan_score integer,
        ADD COLUMN IF NOT EXISTS latest_scan_tier tier,
        ADD COLUMN IF NOT EXISTS latest_scanned_at timestamptz
"""

_LISTED = "WHERE archived = false AND visibility = 'public'"

_INDEXES: dict[str, str] = {
    "idx_catalog_items_list_popularity": (
        f"ON catalog_items (popularity_score DESC, slug) {_LISTED}"
    ),
    "idx_catalog_items_list_score_asc": f"ON catalog_items (latest_scan_score, slug) {_LISTED}",
    "idx_catalog_items_list_score_desc": (
        f"ON catalog_items (latest_scan_score DESC NULLS LAST, slug) {_LISTED}"
    ),
    "idx_catalog_items_list_kind_score": (
        f"ON catalog_items (kind, latest_scan_score DESC NULLS LAST, slug) {_LISTED}"
    ),
    "idx_catalog_items_list_scanned_at": (
        f"ON catalog_items (latest_scanned_at DESC, slug) {_LISTED} "
        "AND latest_scanned_at IS NOT NULL"
    ),
    "idx_scan_runs_feed": (
        "ON scan_runs (scanned_at DESC, id DESC) "
        "WHERE visibility = 'public' AND source NOT IN ('ingestion', 'rescan_rules')"
    ),
}


def _add_columns_with_retry(conn: sa.Connection) -> None:
    conn.execute(sa.text("SET lock_timeout = '3s'"))
    try:
        for attempt in range(1, _ALTER_ATTEMPTS + 1):
            try:
                conn.execute(sa.text(_ADD_COLUMNS))
                return
            except sa.exc.DBAPIError as exc:
                sqlstate = getattr(exc.orig, "sqlstate", None)
                if sqlstate != _LOCK_NOT_AVAILABLE or attempt == _ALTER_ATTEMPTS:
                    raise
                time.sleep(_ALTER_PAUSE_S)
    finally:
        conn.execute(sa.text("RESET lock_timeout"))


def upgrade() -> None:
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        _add_columns_with_retry(conn)
        for name, definition in _INDEXES.items():
            conn.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
            conn.execute(sa.text(f"CREATE INDEX CONCURRENTLY {name} {definition}"))


def downgrade() -> None:
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        for name in _INDEXES:
            conn.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
        conn.execute(
            sa.text(
                """
                ALTER TABLE catalog_items
                    DROP COLUMN IF EXISTS latest_scan_id,
                    DROP COLUMN IF EXISTS latest_scan_score,
                    DROP COLUMN IF EXISTS latest_scan_tier,
                    DROP COLUMN IF EXISTS latest_scanned_at
                """
            )
        )
