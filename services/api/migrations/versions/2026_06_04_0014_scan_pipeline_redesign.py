"""scan pipeline redesign — unified scan recency + repo_fetch_state + rescan_rules

Revision ID: 0014_scan_pipeline_redesign
Revises: 0013_add_ingestion_runs
Create Date: 2026-06-04

The collect-and-scan redesign: every indexed public-github capability is scanned
by a durable Procrastinate job, change-gated + content-addressed.

Schema changes (all reversible):
  1. `scan_source` enum gains `rescan_rules` (the rule/engine version re-eval that
     re-scores from stored bytes — no GitHub re-crawl).
  2. `catalog_items` collapses the two scan-depth recency columns
     (`last_deep_scan_at` / `last_lite_scan_at`, migration 0012) into the unified
     queue-of-record set: `last_scanned_at` + `scanned_rubric_version` +
     `scanned_engine_version` + `last_checked_at`. `last_scanned_at` is backfilled
     from the old columns BEFORE they are dropped (no data loss for already-scanned
     rows).
  3. NEW internal table `repo_fetch_state` — per-repo conditional-fetch validators
     (etag / last-modified / resolved HEAD sha) so an unchanged repo costs a free
     304 against the shared GitHub App-token budget.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_scan_pipeline_redesign"
down_revision: str | None = "0013_add_ingestion_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# scan_source value set BEFORE this migration (0009). Used to rebuild the enum on
# downgrade (Postgres can't drop a single enum value in place).
_SCAN_SOURCE_PRE = ("submission", "ingestion", "rescan_drift", "rescan_appeal")


def upgrade() -> None:
    # 1. scan_source += rescan_rules. PG12+ allows ADD VALUE inside a transaction
    #    as long as the value isn't used in the same transaction (it isn't here).
    op.execute("ALTER TYPE scan_source ADD VALUE IF NOT EXISTS 'rescan_rules'")

    # 2. Unified scan-recency columns.
    op.add_column(
        "catalog_items",
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "catalog_items",
        sa.Column("scanned_rubric_version", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "catalog_items",
        sa.Column("scanned_engine_version", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "catalog_items",
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Backfill last_scanned_at (+ last_checked_at) from the depth columns BEFORE
    # dropping them. GREATEST ignores NULLs (NULL only if both are NULL).
    op.execute(
        """
        UPDATE catalog_items
        SET last_scanned_at = GREATEST(last_deep_scan_at, last_lite_scan_at),
            last_checked_at = GREATEST(last_deep_scan_at, last_lite_scan_at)
        WHERE last_deep_scan_at IS NOT NULL OR last_lite_scan_at IS NOT NULL
        """
    )

    op.drop_index("idx_catalog_items_last_lite_scan_at", table_name="catalog_items")
    op.drop_index("idx_catalog_items_last_deep_scan_at", table_name="catalog_items")
    op.drop_column("catalog_items", "last_lite_scan_at")
    op.drop_column("catalog_items", "last_deep_scan_at")

    op.create_index("idx_catalog_items_last_scanned_at", "catalog_items", ["last_scanned_at"])
    op.create_index("idx_catalog_items_last_checked_at", "catalog_items", ["last_checked_at"])

    # 3. repo_fetch_state — per-repo conditional-fetch validators.
    op.create_table(
        "repo_fetch_state",
        sa.Column("github_url", sa.String(length=1024), primary_key=True, nullable=False),
        sa.Column("etag", sa.String(length=255), nullable=True),
        sa.Column("last_modified", sa.String(length=255), nullable=True),
        sa.Column("resolved_ref_sha", sa.String(length=40), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("repo_fetch_state")

    op.drop_index("idx_catalog_items_last_checked_at", table_name="catalog_items")
    op.drop_index("idx_catalog_items_last_scanned_at", table_name="catalog_items")

    # Re-create the depth columns + indexes (mirror migration 0012).
    op.add_column(
        "catalog_items",
        sa.Column("last_deep_scan_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "catalog_items",
        sa.Column("last_lite_scan_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Best-effort restore: the unified column maps back to the deep slot.
    op.execute(
        "UPDATE catalog_items SET last_deep_scan_at = last_scanned_at "
        "WHERE last_scanned_at IS NOT NULL"
    )
    op.create_index("idx_catalog_items_last_deep_scan_at", "catalog_items", ["last_deep_scan_at"])
    op.create_index("idx_catalog_items_last_lite_scan_at", "catalog_items", ["last_lite_scan_at"])

    op.drop_column("catalog_items", "last_checked_at")
    op.drop_column("catalog_items", "scanned_engine_version")
    op.drop_column("catalog_items", "scanned_rubric_version")
    op.drop_column("catalog_items", "last_scanned_at")

    # Rebuild scan_source WITHOUT rescan_rules (PG can't drop an enum value in
    # place). Re-map any rows using the dropped value to the closest survivor.
    values = ", ".join(f"'{v}'" for v in _SCAN_SOURCE_PRE)
    op.execute("UPDATE scans SET source = 'rescan_drift' WHERE source = 'rescan_rules'")
    op.execute("UPDATE scan_runs SET source = 'rescan_drift' WHERE source = 'rescan_rules'")
    op.execute("ALTER TYPE scan_source RENAME TO scan_source_old")
    op.execute(f"CREATE TYPE scan_source AS ENUM ({values})")
    op.execute(
        "ALTER TABLE scans ALTER COLUMN source TYPE scan_source USING source::text::scan_source"
    )
    op.execute(
        "ALTER TABLE scan_runs ALTER COLUMN source TYPE scan_source USING source::text::scan_source"
    )
    op.execute("DROP TYPE scan_source_old")
