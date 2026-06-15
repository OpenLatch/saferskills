"""drop agent_verify_waitlist (verify-tier demand-capture removed)

Revision ID: 0022_drop_agent_verify_waitlist
Revises: 0021_agent_kind_tally
Create Date: 2026-06-15

The "Request independent verification" waitlist tile on the Agent Report was
removed, so its backing store goes with it. Reverses the `agent_verify_waitlist`
half of 0020 (the `agent_runs.vendor_reply*` columns + the right-of-reply stay):

- drop the `agent_verify_waitlist` table + `idx_agent_verify_waitlist_created`;
- narrow `chk_rate_limits_bucket` back to the pre-0020 set (drop the
  `agent_verify_waitlist` bucket), purging any live counter rows on it first so
  the narrowed CHECK validates against existing rows.

Reversible — `downgrade()` re-creates the table + index and re-widens the CHECK.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_drop_agent_verify_waitlist"
down_revision: str | None = "0021_agent_kind_tally"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# `rate_limits.bucket` CHECK lineage: 0001 -> 0006 -> 0008 -> 0016 -> 0019
# (+agent_scan_submit) -> 0020 (+agent_verify_waitlist) -> here (-agent_verify_waitlist).
_WITHOUT_WAITLIST = (
    "scan_submit",
    "scan_read",
    "item_read",
    "item_list",
    "artifact_download",
    "private_lookup",
    "cli_scan_submit",
    "agent_scan_submit",
)
_WITH_WAITLIST = (*_WITHOUT_WAITLIST, "agent_verify_waitlist")


def _quoted(values: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _bucket_check(values: Sequence[str]) -> str:
    return f"bucket IN ({_quoted(values)})"


def upgrade() -> None:
    # Purge any live rate-limit counters keyed on the removed bucket so the
    # narrowed CHECK validates against the existing rows.
    op.execute("DELETE FROM rate_limits WHERE bucket = 'agent_verify_waitlist'")
    op.drop_constraint("chk_rate_limits_bucket", "rate_limits", type_="check")
    op.create_check_constraint(
        "chk_rate_limits_bucket", "rate_limits", _bucket_check(_WITHOUT_WAITLIST)
    )

    op.drop_index("idx_agent_verify_waitlist_created", table_name="agent_verify_waitlist")
    op.drop_table("agent_verify_waitlist")


def downgrade() -> None:
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

    op.drop_constraint("chk_rate_limits_bucket", "rate_limits", type_="check")
    op.create_check_constraint(
        "chk_rate_limits_bucket", "rate_limits", _bucket_check(_WITH_WAITLIST)
    )
