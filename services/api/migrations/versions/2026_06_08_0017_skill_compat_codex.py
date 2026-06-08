"""Widen the `skill` agent_compatibility set to the skill-capable agents.

Revision ID: 0017_skill_compat_codex
Revises: 0016_cli_pow_spent
Create Date: 2026-06-08

The deterministic kind→agents mapping (``app/services/agent_compat.py``) was
written at W2 with the assumption that the Claude Skills (SKILL.md) format was
Claude-only (``claude-code`` + the Claude-compatible ``openclaw``). Since then
OpenAI Codex, GitHub Copilot, and Gemini have each shipped a native ``skills/``
surface — and the install CLI already treats them as skill-capable (they each
get a ``skill_dir`` in ``cli/src/agents/detect.rs``), so the catalog
``agent_compatibility`` excluding them caused `saferskills install <skill>` to
hide those agents.

Re-derive every existing ``skill`` row to the widened set. ``agent_compatibility``
is pure derived metadata (no per-row manual override), so a blanket re-derive for
the kind is correct — and it matches what new scans now write via
``agent_compatibility_for('skill')``. Only the ``skill`` kind changes; the other
kinds keep their 0003 mapping. Reversible: downgrade restores the Claude-only set.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "0017_skill_compat_codex"
down_revision: str | None = "0016_cli_pow_spent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SKILL_WIDENED = '["claude-code","codex","copilot","gemini","openclaw"]'
_SKILL_CLAUDE_ONLY = '["claude-code","openclaw"]'


def upgrade() -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE catalog_items
            SET agent_compatibility = '{_SKILL_WIDENED}'::jsonb
            WHERE kind = 'skill'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE catalog_items
            SET agent_compatibility = '{_SKILL_CLAUDE_ONLY}'::jsonb
            WHERE kind = 'skill'
            """
        )
    )
