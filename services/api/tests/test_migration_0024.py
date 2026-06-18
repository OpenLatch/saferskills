"""Migration 0024 backfill assertion (I-6.5 plan 02).

`0024_skill_compat_all_agents` re-derives every existing ``skill`` catalog row's
``agent_compatibility`` to the all-eight-agents set (the install CLI's plan-02
renderer now deposits a native form of any skill for every agent). This proves the
backfill SQL: a pre-existing skill row carrying the OLD (0017) 5-agent set is
widened by the upgrade and restored by the downgrade — exercised inside the
per-test SAVEPOINT (auto-rolled-back, no committed mutation), so it neither needs
a subprocess alembic nor leaves the DB off head.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog_item import CatalogItem
from app.services.agent_compat import ALL_AGENTS

# The exact backfill statements the 0024 migration runs (kept in lockstep).
_SKILL_ALL_AGENTS = (
    '["claude-code","cursor","codex","copilot","windsurf","cline","gemini","openclaw"]'
)
_SKILL_CODEX_SET = '["claude-code","codex","copilot","gemini","openclaw"]'

_UPGRADE = sa.text(
    f"UPDATE catalog_items SET agent_compatibility = '{_SKILL_ALL_AGENTS}'::jsonb "
    "WHERE kind = 'skill'"
)
_DOWNGRADE = sa.text(
    f"UPDATE catalog_items SET agent_compatibility = '{_SKILL_CODEX_SET}'::jsonb "
    "WHERE kind = 'skill'"
)


async def _compat(session: AsyncSession, item_id: uuid.UUID) -> list[str]:
    row = await session.execute(
        sa.text("SELECT agent_compatibility FROM catalog_items WHERE id = :id"),
        {"id": str(item_id)},
    )
    return list(row.scalar_one())


@pytest.mark.asyncio
async def test_0024_backfills_skill_rows_to_all_agents(db_session: AsyncSession) -> None:
    suffix = uuid.uuid4().hex[:8]
    # A pre-existing skill row carrying the OLD (0017) 5-agent compat set, and a
    # non-skill row that must be left untouched.
    skill = CatalogItem(
        kind="skill",
        slug=f"acme--kit--skill-{suffix}",
        display_name="A skill",
        github_url=f"https://github.com/acme/kit-{suffix}",
        github_org="acme",
        github_repo=f"kit-{suffix}",
        default_branch="main",
        popularity_tier="indexed",
        popularity_score=1,
        sources=[],
        agent_compatibility=["claude-code", "codex", "copilot", "gemini", "openclaw"],
    )
    mcp = CatalogItem(
        kind="mcp_server",
        slug=f"acme--kit--mcp-server-{suffix}",
        display_name="An MCP server",
        github_url=f"https://github.com/acme/mcp-{suffix}",
        github_org="acme",
        github_repo=f"mcp-{suffix}",
        default_branch="main",
        popularity_tier="indexed",
        popularity_score=1,
        sources=[],
        agent_compatibility=list(ALL_AGENTS),
    )
    db_session.add_all([skill, mcp])
    await db_session.flush()
    mcp_before = await _compat(db_session, mcp.id)

    # Upgrade → the skill row is widened to all eight; the mcp row is unchanged.
    await db_session.execute(_UPGRADE)
    assert set(await _compat(db_session, skill.id)) == set(ALL_AGENTS)
    assert await _compat(db_session, mcp.id) == mcp_before

    # Downgrade → the skill row is restored to the 0017 5-agent set.
    await db_session.execute(_DOWNGRADE)
    assert await _compat(db_session, skill.id) == [
        "claude-code",
        "codex",
        "copilot",
        "gemini",
        "openclaw",
    ]
