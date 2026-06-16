"""link an agent run to its component scan_run

Revision ID: 0023_agent_component_scan_link
Revises: 0022_drop_agent_verify_waitlist
Create Date: 2026-06-16

Adds the nullable `agent_runs.component_scan_run_id` FK -> `scan_runs(id)`
`ON DELETE SET NULL`. It links the best-effort, CLI-captured component scan (the
`scan --local` upload of the scanned platform's installed capabilities) onto the
agent run so the Agent Report can project that run's per-capability `scans` into the
Component Scores tab. Null on web / `--print-skill` paths (no local filesystem) — the
tab then keeps its honest "Behavior graded as one system" empty state.

`SET NULL` (not CASCADE): deleting a component scan_run (its own unlisted expiry
sweep, a vendor appeal, …) must NOT delete the behavioral agent run — it just drops
the now-dangling link, and the report falls back to the empty tab.

Reversible — `downgrade()` drops the FK + column. (DB-only `x-postgresql-extra-
columns` on `agent-scan-report.schema.json`; the generated `AgentRun` model carries
the matching `mapped_column`, not the wire entity.)
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0023_agent_component_scan_link"
down_revision: str | None = "0022_drop_agent_verify_waitlist"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("component_scan_run_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_runs_component_scan_run_id",
        "agent_runs",
        "scan_runs",
        ["component_scan_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_agent_runs_component_scan_run_id", "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "component_scan_run_id")
