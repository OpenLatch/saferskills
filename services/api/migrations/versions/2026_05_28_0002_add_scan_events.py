"""Add scan_events table for SSE catch-up replay.

Revision ID: 0002_add_scan_events
Revises: 0001_initial_scan_surface
Create Date: 2026-05-28

Phase B (W4-W5) — the in-process queue worker appends a row per stage boundary
during a scan. SSE consumers replay every row with `event_seq > last_event_id`
from this table, then subscribe to PostgreSQL `LISTEN scan_progress_<id>` for
live deltas (per D-FE-09 + D-FE-34).

The composite `(scan_id, event_seq)` is both indexed (lookup by scan) and
unique (monotonic per-scan ordering). `payload` is a free-form JSONB blob the
worker fills with per-stage detail (detector list, current rule, etc.).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# Revision identifiers, used by Alembic.
revision: str = "0002_add_scan_events"
down_revision: str | None = "0001_initial_scan_surface"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


STAGE_VALUES = (
    "fetch",
    "index",
    "security",
    "supply_chain",
    "maintenance",
    "transparency",
    "community",
    "score",
    "sign",
    "done",
)
SCAN_EVENT_STATUS_VALUES = ("pending", "running", "completed", "failed")


def _check_in(column: str, values: Sequence[str], name: str) -> sa.CheckConstraint:
    quoted = ", ".join(f"'{v}'" for v in values)
    return sa.CheckConstraint(f"{column} IN ({quoted})", name=name)


def upgrade() -> None:
    op.create_table(
        "scan_events",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "scan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_seq", sa.Integer, nullable=False),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("completion_pct", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="'pending'"),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column(
            "emitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("scan_id", "event_seq", name="uq_scan_events_scan_id_seq"),
        _check_in("stage", STAGE_VALUES, "chk_scan_events_stage"),
        _check_in("status", SCAN_EVENT_STATUS_VALUES, "chk_scan_events_status"),
        sa.CheckConstraint(
            "completion_pct BETWEEN 0 AND 100",
            name="chk_scan_events_completion_pct",
        ),
    )
    op.create_index("idx_scan_events_scan_id_seq", "scan_events", ["scan_id", "event_seq"])


def downgrade() -> None:
    op.drop_index("idx_scan_events_scan_id_seq", table_name="scan_events")
    op.drop_table("scan_events")
