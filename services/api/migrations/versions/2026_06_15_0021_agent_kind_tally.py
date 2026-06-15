"""add agent_runs.kind_tally (per-kind capability inventory)

Revision ID: 0021_agent_kind_tally
Revises: 0020_agent_directory_surface
Create Date: 2026-06-15

Adds the nullable `agent_runs.kind_tally` JSONB column — the per-kind capability
inventory ({skill, hook, mcp, plugin, rules} → count) that backs the `/agents`
dossier-card capability stack. DB-only (`x-postgresql-extra-columns` on
`agent-scan-report.schema.json`) — projected onto the directory summary's
`capability_tally` in `app/agent_scan/directory.py`, NEVER on the generated wire
entity / openapi.json. NULL for real scans until the submit/grade flow captures a
component inventory; the directory coalesces NULL → an all-zero tally (no icons).

Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_agent_kind_tally"
down_revision: str | None = "0020_agent_directory_surface"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("kind_tally", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "kind_tally")
