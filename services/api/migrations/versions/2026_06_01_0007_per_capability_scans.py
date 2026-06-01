"""Per-capability scans grouped by scan_runs.

Revision ID: 0007_per_capability_scans
Revises: 0006_add_artifact_blobs
Create Date: 2026-06-01

One repo scan now discovers + scores N capabilities (a Skill, an MCP server,
hooks, …) and fans out to N `scans` rows grouped under one `scan_runs` row.

This migration:
- adds `scan_runs` (repo aggregate = mean of capability scores + by-kind tally);
- adds `scans.scan_run_id` (SET NULL) + `scans.component_path`;
- re-keys `scan_events` onto the run (`scan_run_id`; `scan_id` becomes nullable);
- drops `UNIQUE(catalog_items.github_url)` and replaces it with a non-unique
  index — several capabilities now legitimately share one repo URL;
- backfills one `scan_runs` row per existing `scans` row (every legacy/seed scan
  becomes a 1-capability run), so item-detail / version-history keep working.

`downgrade()` is best-effort: re-adding `UNIQUE(github_url)` only succeeds on a
DB that has not yet fanned out multiple capabilities onto a shared URL.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# Revision identifiers, used by Alembic.
revision: str = "0007_per_capability_scans"
down_revision: str | None = "0006_add_artifact_blobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIER_VALUES = ("green", "yellow", "orange", "red", "unscoped")
SCAN_SOURCE_VALUES = ("submission", "ingestion", "rescan_drift", "rescan_appeal")
SCAN_RUN_STATUS_VALUES = ("pending", "running", "completed", "failed")


def _quoted(values: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    # ── scan_runs ───────────────────────────────────────────────────────────
    op.create_table(
        "scan_runs",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("github_url", sa.String(500), nullable=False),
        sa.Column("ref_sha", sa.String(40), nullable=True),
        sa.Column("repo_aggregate_score", sa.Integer, nullable=False, server_default="0"),
        sa.Column("repo_tier", sa.String(20), nullable=False, server_default="'unscoped'"),
        sa.Column("kind_tally", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("capability_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rubric_version", sa.String(40), nullable=False),
        sa.Column("engine_version", sa.String(40), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("file_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="'pending'"),
        sa.Column(
            "scanned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
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
        sa.UniqueConstraint("idempotency_key", name="uq_scan_runs_idempotency_key"),
        sa.CheckConstraint(
            "repo_aggregate_score BETWEEN 0 AND 100", name="chk_scan_runs_repo_aggregate_score"
        ),
        sa.CheckConstraint(
            f"repo_tier IN ({_quoted(TIER_VALUES)})", name="chk_scan_runs_repo_tier"
        ),
        sa.CheckConstraint(
            f"source IN ({_quoted(SCAN_SOURCE_VALUES)})", name="chk_scan_runs_source"
        ),
        sa.CheckConstraint(
            f"status IN ({_quoted(SCAN_RUN_STATUS_VALUES)})", name="chk_scan_runs_status"
        ),
    )
    op.create_index("idx_scan_runs_scanned_at", "scan_runs", ["scanned_at"])

    # ── scans: link to a run + record the scanned subtree ─────────────────────
    op.add_column("scans", sa.Column("scan_run_id", UUID(as_uuid=True), nullable=True))
    op.add_column("scans", sa.Column("component_path", sa.String(1024), nullable=True))
    op.create_foreign_key(
        "fk_scans_scan_run_id", "scans", "scan_runs", ["scan_run_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("idx_scans_scan_run_id", "scans", ["scan_run_id"])

    # ── scan_events: re-key progress onto the run ─────────────────────────────
    op.add_column("scan_events", sa.Column("scan_run_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_scan_events_scan_run_id",
        "scan_events",
        "scan_runs",
        ["scan_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_scan_events_scan_run_id", "scan_events", ["scan_run_id"])
    # scan_id is now optional (run-level events leave it null).
    op.alter_column("scan_events", "scan_id", nullable=True)

    # ── catalog_items: several capabilities may share one repo URL ────────────
    op.drop_constraint("uq_catalog_items_github_url", "catalog_items", type_="unique")
    op.create_index("idx_catalog_items_github_url", "catalog_items", ["github_url"])

    # ── backfill: one scan_runs row per existing scan (1-capability run) ──────
    # Copies score/url/ref/versions/source; reuses the scan's idempotency_key so
    # the key stays unique on scan_runs. kind_tally derived from the item kind.
    op.execute(
        sa.text(
            """
            INSERT INTO scan_runs (
                id, idempotency_key, github_url, ref_sha, repo_aggregate_score,
                repo_tier, kind_tally, capability_count, rubric_version,
                engine_version, source, latency_ms, file_count, status,
                scanned_at, created_at, updated_at
            )
            SELECT
                gen_random_uuid(), s.idempotency_key, s.github_url, s.ref_sha,
                s.aggregate_score, s.tier, jsonb_build_object(ci.kind, 1), 1,
                s.rubric_version, s.engine_version, s.source, s.latency_ms, 0,
                CASE WHEN s.aggregate_score = 0 THEN 'running' ELSE 'completed' END,
                s.scanned_at, s.created_at, s.updated_at
            FROM scans s
            JOIN catalog_items ci ON ci.id = s.catalog_item_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE scans s
            SET scan_run_id = r.id
            FROM scan_runs r
            WHERE r.idempotency_key = s.idempotency_key
            """
        )
    )


def downgrade() -> None:
    # Re-adding UNIQUE(github_url) only succeeds on a DB with no shared-URL
    # fan-out; on a fanned-out DB it raises (documented best-effort).
    op.drop_index("idx_scan_events_scan_run_id", table_name="scan_events")
    op.drop_constraint("fk_scan_events_scan_run_id", "scan_events", type_="foreignkey")
    op.alter_column("scan_events", "scan_id", nullable=False)
    op.drop_column("scan_events", "scan_run_id")

    op.drop_index("idx_scans_scan_run_id", table_name="scans")
    op.drop_constraint("fk_scans_scan_run_id", "scans", type_="foreignkey")
    op.drop_column("scans", "component_path")
    op.drop_column("scans", "scan_run_id")

    op.drop_index("idx_catalog_items_github_url", table_name="catalog_items")
    op.create_unique_constraint("uq_catalog_items_github_url", "catalog_items", ["github_url"])

    op.drop_index("idx_scan_runs_scanned_at", table_name="scan_runs")
    op.drop_table("scan_runs")
