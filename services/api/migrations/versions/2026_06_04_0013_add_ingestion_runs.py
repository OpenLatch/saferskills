"""add ingestion_runs (eagle-eye health view)

Revision ID: 0013_add_ingestion_runs
Revises: 0012_phase_c_scan_recency
Create Date: 2026-06-04

Ingestion observability ("eagle-eye"). Creates the first-class `ingestion_runs`
table — one row per cycle attempt, written at the `tasks.py` chokepoint in
independent sessions. Backs the enriched `GET /api/v1/admin/sources` snapshot +
the `…/{source}/runs` drill-down + the `saferskills-admin sources dashboard` TUI.

Internal hand-written store (no JSON-Schema source, no wire DTO) — mirrors
`crawler_cursors` / `upload_files`. Swept after 90 days (`app/core/sweeps.py`).
Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_add_ingestion_runs"
down_revision: str | None = "0012_phase_c_scan_recency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("items_seen", sa.Integer(), nullable=True),
        sa.Column("items_added", sa.Integer(), nullable=True),
        sa.Column("items_updated", sa.Integer(), nullable=True),
        sa.Column("http_304_count", sa.Integer(), nullable=True),
        sa.Column("http_5xx_count", sa.Integer(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("error_class", sa.String(200), nullable=True),
        sa.Column("error_message", sa.String(2048), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "chk_ingestion_runs_status",
        "ingestion_runs",
        "status IN ('running','succeeded','failed')",
    )
    op.create_check_constraint(
        "chk_ingestion_runs_trigger",
        "ingestion_runs",
        "trigger IN ('scheduled','manual','force')",
    )
    op.create_index(
        "idx_ingestion_runs_source_started",
        "ingestion_runs",
        ["source", sa.text("started_at DESC")],
    )
    op.create_index(
        "idx_ingestion_runs_running",
        "ingestion_runs",
        ["status"],
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index("idx_ingestion_runs_running", table_name="ingestion_runs")
    op.drop_index("idx_ingestion_runs_source_started", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
