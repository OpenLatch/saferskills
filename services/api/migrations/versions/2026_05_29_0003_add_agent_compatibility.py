"""Add agent_compatibility to catalog_items.

Revision ID: 0003_add_agent_compatibility
Revises: 0002_add_scan_events
Create Date: 2026-05-29

Phase B catalog rewrite — the catalog Agent-compatibility filter needs a per-item
closed-enum list of agent platforms. The column is a JSONB array defaulting to
`[]`. Existing rows are backfilled with the deterministic kind→agents mapping
documented in ``docs/methodology.md`` § Agent compatibility (mirrored in
``app/services/agent_compat.py::agent_compatibility_for``). Keep the CASE below in
sync with that helper — a mapping change ships a fresh backfill migration.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# Revision identifiers, used by Alembic.
revision: str = "0003_add_agent_compatibility"
down_revision: str | None = "0002_add_scan_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "catalog_items",
        sa.Column(
            "agent_compatibility",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    # Deterministic kind→agents backfill (mirrors agent_compatibility_for).
    op.execute(
        sa.text(
            """
            UPDATE catalog_items SET agent_compatibility = CASE kind
                WHEN 'mcp_server' THEN
                    '["claude-code","cursor","codex","copilot","windsurf","cline","gemini","openclaw"]'::jsonb
                WHEN 'skill'  THEN '["claude-code","openclaw"]'::jsonb
                WHEN 'plugin' THEN '["claude-code","openclaw"]'::jsonb
                WHEN 'hook'   THEN '["claude-code","openclaw"]'::jsonb
                WHEN 'rules'  THEN '["cursor","windsurf","cline","copilot"]'::jsonb
                ELSE '[]'::jsonb
            END
            """
        )
    )


def downgrade() -> None:
    op.drop_column("catalog_items", "agent_compatibility")
