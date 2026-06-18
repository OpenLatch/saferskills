"""Widen the `skill` agent_compatibility set to ALL eight agents.

Revision ID: 0024_skill_compat_all_agents
Revises: 0023_agent_component_scan_link
Create Date: 2026-06-18

The install CLI's general `kind:skill → native form` renderer (I-6.5 plan 02,
``cli/src/agents/writers/render.rs``) now deposits a native form of any skill for
EVERY agent — verbatim ``SKILL.md`` for the skills-dir agents (Claude Code,
OpenClaw, Codex, Copilot, Gemini), a ``.mdc`` / rules ``.md`` for the rules-dir
agents (Cursor, Windsurf, Cline), and a shared ``AGENTS.md`` / ``GEMINI.md`` marker
block for Codex/Copilot/Gemini. The renderer makes the compatibility claim TRUE, so
the catalog must assert ``skill`` for all eight (previously the 5-agent Codex set
from ``0017_skill_compat_codex``).

Re-derive every existing ``skill`` row to the all-agents set. ``agent_compatibility``
is pure derived metadata (no per-row manual override), so a blanket re-derive for
the kind is correct — and it matches what new scans now write via
``agent_compatibility_for('skill')``. Only the ``skill`` kind changes; the other
kinds keep their 0003 mapping. Reversible: downgrade restores the 0017 5-agent set.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "0024_skill_compat_all_agents"
down_revision: str | None = "0023_agent_component_scan_link"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ALL eight canonical agent ids, in catalog-enum order (mirrors
# app/services/agent_compat.py::ALL_AGENTS).
_SKILL_ALL_AGENTS = (
    '["claude-code","cursor","codex","copilot","windsurf","cline","gemini","openclaw"]'
)
# The 0017 set this revision widens (the downgrade target).
_SKILL_CODEX_SET = '["claude-code","codex","copilot","gemini","openclaw"]'


def upgrade() -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE catalog_items
            SET agent_compatibility = '{_SKILL_ALL_AGENTS}'::jsonb
            WHERE kind = 'skill'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE catalog_items
            SET agent_compatibility = '{_SKILL_CODEX_SET}'::jsonb
            WHERE kind = 'skill'
            """
        )
    )
