"""add agent-directory surface (I-5.6 Phase C)

Revision ID: 0020_agent_directory_surface
Revises: 0019_agent_scan
Create Date: 2026-06-10

I-5.6 Phase C (the public web surfaces for Agent Scan). Adds:

- `agent_runs.vendor_reply` (varchar 1000, nullable) + `agent_runs.vendor_reply_at`
  (timestamptz, nullable) — the capability-token holder's ≤500-char public
  right-of-reply, persisted on the run + rendered read-only on the report (D-5.6-08,
  §13). DB-only (`x-postgresql-extra-columns` on `agent-scan-report.schema.json`) —
  projected onto the hand-written report DTO, NOT on the generated wire entity.
- `agent_verify_waitlist` — internal hand-written demand-capture store backing the
  "Request independent verification" waitlist tile on every report (D-5.6-08).
  Redacted IP + optional email at write time (`privacy.md`); rows retained.
- `chk_rate_limits_bucket` gains `agent_verify_waitlist` (VARCHAR + CHECK — the
  `rate_limits` table is an internal hand-written store, not a native-enum column).
  Lineage: 0001 -> 0006 -> 0008 -> 0016 -> 0019 -> here.

Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_agent_directory_surface"
down_revision: str | None = "0019_agent_scan"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# `rate_limits.bucket` CHECK lineage: 0001 -> 0006 (+artifact_download) ->
# 0008 (+private_lookup) -> 0016 (+cli_scan_submit) -> 0019 (+agent_scan_submit) ->
# here (+agent_verify_waitlist).
_OLD_BUCKETS = (
    "scan_submit",
    "scan_read",
    "item_read",
    "item_list",
    "artifact_download",
    "private_lookup",
    "cli_scan_submit",
    "agent_scan_submit",
)
_NEW_BUCKETS = (*_OLD_BUCKETS, "agent_verify_waitlist")


def _quoted(values: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _bucket_check(values: Sequence[str]) -> str:
    return f"bucket IN ({_quoted(values)})"


def upgrade() -> None:
    # 1. agent_runs vendor right-of-reply columns (DB-only extra-columns).
    op.add_column("agent_runs", sa.Column("vendor_reply", sa.String(1000), nullable=True))
    op.add_column(
        "agent_runs", sa.Column("vendor_reply_at", sa.DateTime(timezone=True), nullable=True)
    )

    # 2. agent_verify_waitlist — internal demand-capture store (no JSON Schema, no wire DTO).
    op.create_table(
        "agent_verify_waitlist",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("redacted_ip", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_agent_verify_waitlist_created", "agent_verify_waitlist", ["created_at"])

    # 3. rate_limits CHECK += agent_verify_waitlist (drop + recreate).
    op.drop_constraint("chk_rate_limits_bucket", "rate_limits", type_="check")
    op.create_check_constraint("chk_rate_limits_bucket", "rate_limits", _bucket_check(_NEW_BUCKETS))


def downgrade() -> None:
    op.drop_constraint("chk_rate_limits_bucket", "rate_limits", type_="check")
    op.create_check_constraint("chk_rate_limits_bucket", "rate_limits", _bucket_check(_OLD_BUCKETS))

    op.drop_index("idx_agent_verify_waitlist_created", table_name="agent_verify_waitlist")
    op.drop_table("agent_verify_waitlist")

    op.drop_column("agent_runs", "vendor_reply_at")
    op.drop_column("agent_runs", "vendor_reply")
