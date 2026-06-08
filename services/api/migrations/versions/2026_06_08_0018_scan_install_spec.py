"""Add the per-capability `scans.install_spec` JSONB column.

Revision ID: 0018_scan_install_spec
Revises: 0017_skill_compat_codex
Create Date: 2026-06-08

The `saferskills` install CLI installs/uninstalls/updates every capability kind
(skill, mcp_server, hook, plugin, rules) across every compatible agent. To do so
deterministically — without re-parsing the artifact zip CLI-side — the scan now
persists a per-capability ``install_spec`` derived from the same already-public
bytes the snapshot tier serves (``app/scan/discovery.py::build_install_spec``).
It is surfaced on the report DTO the CLI fetches.

JSONB, so no ``CREATE TYPE`` / ``KNOWN_ENUMS`` entry. Backfill is deferred:
existing scans get NULL and the ``rescan_rules`` trigger repopulates them from
stored bytes over time. Reversible: downgrade drops the column.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers, used by Alembic.
revision: str = "0018_scan_install_spec"
down_revision: str | None = "0017_skill_compat_codex"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scans",
        sa.Column("install_spec", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scans", "install_spec")
