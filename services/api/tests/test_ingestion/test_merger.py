"""Tests for app.ingestion.framework.merger.MergeEngine.

NOTE: These tests currently xfail due to an ORM-to-DB column name mismatch in
the generated model (app/models/generated/catalog_item.py):

  - ORM attribute: consecutive404_count  →  maps to DB column consecutive404_count
  - Actual DB column:                         consecutive_404_count

  - ORM attribute: last_seen200_at       →  maps to DB column last_seen200_at
  - Actual DB column:                         last_seen_200_at

The JSON Schema source (schemas/catalog-item.schema.json) uses camelCase
`consecutive404Count` and `lastSeen200At`. The code generator converts these to
`consecutive404_count` / `last_seen200_at` (treating the numeric suffix as part
of the word), but the migration (0010_catalog_full_projection) creates
`consecutive_404_count` / `last_seen_200_at`. The generated model needs
`name="consecutive_404_count"` / `name="last_seen_200_at"` column overrides
to match the actual DB schema — or the migration must use the names the generator
produces.

Fix: add `name="consecutive_404_count"` and `name="last_seen_200_at"` to the
`x-postgresql-extra-columns` entries in schemas/catalog-item.schema.json, then
regenerate, OR update migration 0010 to use `consecutive404_count` /
`last_seen200_at`.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.framework.merger import MergeEngine
from app.models import CatalogItem, ItemSource, MergeCandidate
from tests.test_ingestion.conftest import make_normalized


def _ORM_BUG(fn: Any) -> Any:
    # ORM column-name bug fixed (migration + merger aligned to generated
    # column names); marker kept as a no-op so existing decorators stay valid.
    return fn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HASH_A = "a" * 64
_HASH_B = "b" * 64


async def _count_items(session: AsyncSession, slug_prefix: str = "") -> int:  # pyright: ignore[reportUnusedFunction]
    stmt = select(CatalogItem)
    rows = (await session.execute(stmt)).scalars().all()
    if slug_prefix:
        return sum(1 for r in rows if r.slug.startswith(slug_prefix))
    return len(rows)


# ---------------------------------------------------------------------------
# Tests: new item → 'added'
# ---------------------------------------------------------------------------


@_ORM_BUG
@pytest.mark.asyncio
async def test_upsert_new_item_returns_added(db_session: AsyncSession) -> None:
    engine = MergeEngine(db_session)
    n = make_normalized(github_org="acme", github_repo="my-skill", display_name="my-skill")
    outcome = await engine.upsert(n, raw_hash=_HASH_A, source="github_topics")
    assert outcome == "added"


@_ORM_BUG
@pytest.mark.asyncio
async def test_upsert_new_item_creates_catalog_row(db_session: AsyncSession) -> None:
    engine = MergeEngine(db_session)
    n = make_normalized(github_org="acme", github_repo="new-skill", display_name="new-skill")
    await engine.upsert(n, raw_hash=_HASH_A, source="github_topics")
    await db_session.flush()

    row = (
        await db_session.execute(select(CatalogItem).where(CatalogItem.github_org == "acme"))
    ).scalar_one_or_none()
    assert row is not None
    assert "acme--new-skill" in row.slug
    assert row.source_kind == "github"
    assert row.visibility == "public"


@_ORM_BUG
@pytest.mark.asyncio
async def test_upsert_new_item_creates_item_source(db_session: AsyncSession) -> None:
    engine = MergeEngine(db_session)
    n = make_normalized(
        github_org="acme",
        github_repo="skill-with-source",
        display_name="skill-with-source",
        source_url="https://github.com/acme/skill-with-source",
    )
    await engine.upsert(n, raw_hash=_HASH_A, source="github_topics")
    await db_session.flush()

    item = (
        await db_session.execute(
            select(CatalogItem).where(CatalogItem.github_repo == "skill-with-source")
        )
    ).scalar_one_or_none()
    assert item is not None

    src = (
        await db_session.execute(select(ItemSource).where(ItemSource.catalog_item_id == item.id))
    ).scalar_one_or_none()
    assert src is not None
    assert src.registry_id == "github_topics"


# ---------------------------------------------------------------------------
# Tests: same item again → 'updated', GitHub-wins conflict recorded
# ---------------------------------------------------------------------------


@_ORM_BUG
@pytest.mark.asyncio
async def test_upsert_existing_item_returns_updated(db_session: AsyncSession) -> None:
    engine = MergeEngine(db_session)
    n = make_normalized(
        github_org="acme",
        github_repo="updatable",
        display_name="updatable",
        description="first",
    )
    await engine.upsert(n, raw_hash=_HASH_A, source="github_topics")
    await db_session.flush()

    # Second upsert — same slug, different hash
    n2 = make_normalized(
        github_org="acme",
        github_repo="updatable",
        display_name="updatable",
        description="second",
    )
    outcome = await engine.upsert(n2, raw_hash=_HASH_B, source="github_topics")
    assert outcome == "updated"


@_ORM_BUG
@pytest.mark.asyncio
async def test_github_wins_conflict_recorded(db_session: AsyncSession) -> None:
    """When a github source disagrees with the stored description, a conflict entry is recorded."""
    engine = MergeEngine(db_session)
    n_orig = make_normalized(
        github_org="acme",
        github_repo="conflict-skill",
        display_name="conflict-skill",
        description="original",
    )
    await engine.upsert(n_orig, raw_hash=_HASH_A, source="github_topics")
    await db_session.flush()

    # Now a non-github source disagrees — current value wins, conflict logged
    n_npm = make_normalized(
        github_org="acme",
        github_repo="conflict-skill",
        display_name="conflict-skill",
        description="npm-override-attempt",
    )
    await engine.upsert(n_npm, raw_hash=_HASH_B, source="npm")
    await db_session.flush()

    item = (
        await db_session.execute(
            select(CatalogItem).where(CatalogItem.github_repo == "conflict-skill")
        )
    ).scalar_one()
    meta: dict[str, Any] = item.item_metadata or {}  # pyright: ignore[reportUnknownMemberType]
    conflicts: list[dict[str, Any]] = meta.get("conflicts", [])
    assert isinstance(conflicts, list)
    # The current value ("original") wins, conflict entry has chosen=current
    assert any(c.get("chosen") == "current" for c in conflicts), conflicts


# ---------------------------------------------------------------------------
# Tests: no GitHub coordinate → staging row + merge_candidate (fuzzy path)
# ---------------------------------------------------------------------------


@_ORM_BUG
@pytest.mark.asyncio
async def test_fuzzy_path_no_github_coord_inserts_staging_row(
    db_session: AsyncSession,
) -> None:
    engine = MergeEngine(db_session)
    n = make_normalized(
        github_org=None,
        github_repo=None,
        display_name="orphan-skill",
        description="I have no github coord",
    )
    outcome = await engine.upsert(n, raw_hash=_HASH_A, source="npm")
    # outcome is 'added' (no fuzzy match) or 'added_with_merge_candidate'
    assert outcome in {"added", "added_with_merge_candidate"}

    rows = (await db_session.execute(select(CatalogItem))).scalars().all()
    staging = [r for r in rows if r.slug.startswith("pending--")]
    assert len(staging) >= 1


@_ORM_BUG
@pytest.mark.asyncio
async def test_fuzzy_path_creates_merge_candidate_for_similar_name(
    db_session: AsyncSession,
) -> None:
    """Insert an existing canonical item, then insert a no-coord item with a very similar name."""
    engine = MergeEngine(db_session)

    # Insert canonical item first
    n_canonical = make_normalized(
        github_org="acme",
        github_repo="super-mcp-server",
        display_name="super-mcp-server",
    )
    await engine.upsert(n_canonical, raw_hash=_HASH_A, source="github_topics")
    await db_session.flush()

    # Insert fuzzy candidate — name closely matches "super-mcp-server"
    n_fuzzy = make_normalized(
        github_org=None,
        github_repo=None,
        display_name="super-mcp-server",  # identical name → guaranteed match
        description="From mcp registry",
    )
    outcome = await engine.upsert(n_fuzzy, raw_hash=_HASH_B, source="mcp_registry")
    # Should be added_with_merge_candidate since names match
    assert outcome == "added_with_merge_candidate"

    mc_rows = (await db_session.execute(select(MergeCandidate))).scalars().all()
    assert len(mc_rows) >= 1
    assert all(mc.status == "pending" for mc in mc_rows)
