"""add install_events (opt-in install telemetry)

Revision ID: 0015_install_events
Revises: 0014_scan_pipeline_redesign
Create Date: 2026-06-04

I-05 Install CLI (D-05-31). Creates the dedicated `install_events` store — one row
per opt-in install reported by the CLI — backing the real `install_activity`
GROUP-BY aggregate that replaces `items.py::_mock_install_activity`. Creates the
native `agent` PG enum (the 8 canonical agent ids); the `kind` enum already exists
(migration 0009) and is reused.

Internal hand-written store (no JSON-Schema source, no wire DTO) — mirrors
`access_log` / `ingestion_runs`. Rows are RETAINED (redacted IP, closed-enum, no
PII) so the `all_time` count survives. Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_install_events"
down_revision: str | None = "0014_scan_pipeline_redesign"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The 8 canonical agent ids (mirrors app/services/agent_compat.py::AgentName +
# app/models/install_event.py::AGENT_VALUES).
AGENT_VALUES: tuple[str, ...] = (
    "claude-code",
    "cursor",
    "codex",
    "copilot",
    "windsurf",
    "cline",
    "gemini",
    "openclaw",
)
# Pre-existing native `kind` enum (migration 0009) — referenced, not created here.
KIND_VALUES: tuple[str, ...] = ("skill", "mcp_server", "hook", "plugin", "rules")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    # Create the native `agent` enum type idempotently (race-safe on multi-machine
    # boot — same pattern as migration 0009).
    op.execute(
        f"DO $$ BEGIN "
        f"IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'agent') THEN "
        f"CREATE TYPE agent AS ENUM ({_quoted(AGENT_VALUES)}); "
        f"END IF; END $$"
    )

    op.create_table(
        "install_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "catalog_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("catalog_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # create_type=False: the `agent` type is created above; `kind` predates us.
        sa.Column(
            "agent",
            postgresql.ENUM(*AGENT_VALUES, name="agent", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "kind",
            postgresql.ENUM(*KIND_VALUES, name="kind", create_type=False),
            nullable=False,
        ),
        sa.Column("cli_version", sa.String(32), nullable=True),
        sa.Column("redacted_ip", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_install_events_item_created",
        "install_events",
        ["catalog_item_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_install_events_item_created", table_name="install_events")
    op.drop_table("install_events")
    # Drop only the `agent` type we created — `kind` is shared with other tables.
    op.execute("DROP TYPE IF EXISTS agent")
