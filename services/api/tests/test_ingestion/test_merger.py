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

from app.ingestion.framework.base_adapter import NormalizedItem
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


# ---------------------------------------------------------------------------
# Tests: adapter kind hint is honored on the stored column (contract:
# "classifier finalises when None") — regression for the slug/column divergence
# where mcp_registry/npm/pypi items were stored as 'skill' despite an
# 'mcp_server' hint and an mcp-server slug.
# ---------------------------------------------------------------------------


@_ORM_BUG
@pytest.mark.asyncio
async def test_adapter_kind_hint_is_stored_on_column(db_session: AsyncSession) -> None:
    """An mcp_server hint with no enriched manifest must store kind='mcp_server'
    (not the file-classifier default 'skill') and universal agent_compatibility."""
    from app.services.agent_compat import ALL_AGENTS

    engine = MergeEngine(db_session)
    n = make_normalized(
        github_org="acme",
        github_repo="hinted",
        display_name="hinted",
        kind="mcp_server",  # adapter hint; no metadata_files → classifier alone says 'skill'
    )
    await engine.upsert(n, raw_hash=_HASH_A, source="mcp_registry")
    await db_session.flush()

    item = (
        await db_session.execute(select(CatalogItem).where(CatalogItem.github_repo == "hinted"))
    ).scalar_one()
    # Slug already encoded mcp-server from the hint; the column must agree.
    assert item.kind == "mcp_server"
    assert "mcp-server-hinted" in item.slug
    # mcp_server with no transport signal → universal agent compatibility.
    assert set(item.agent_compatibility) == set(ALL_AGENTS)


@_ORM_BUG
@pytest.mark.asyncio
async def test_overlong_license_is_clamped_not_crashed(db_session: AsyncSession) -> None:
    """Regression: a license_spdx longer than the VARCHAR(100) column must be clamped
    (first line, ≤100 chars) rather than aborting the insert with
    StringDataRightTruncationError (the pypi free-form-license crash)."""
    engine = MergeEngine(db_session)
    long_license = "MIT License\n\nCopyright (c) 2026 Acme Corp\n" + ("blah " * 500)
    n = make_normalized(
        github_org="acme",
        github_repo="licensed",
        display_name="licensed",
        license_spdx=long_license,
    )
    outcome = await engine.upsert(n, raw_hash=_HASH_A, source="pypi")
    await db_session.flush()  # would raise StringDataRightTruncationError before the fix
    assert outcome == "added"

    item = (
        await db_session.execute(select(CatalogItem).where(CatalogItem.github_repo == "licensed"))
    ).scalar_one()
    assert item.license_spdx == "MIT License"
    assert len(item.license_spdx) <= 100


# ---------------------------------------------------------------------------
# Tests: re-tier on update from fresh enrichment (the empty-catalog fix).
# A mcp_registry server first ingested without repo signals tiers as `empty`
# (hidden by the default catalog gate); a re-crawl that enriches must lift it.
# ---------------------------------------------------------------------------


@_ORM_BUG
@pytest.mark.asyncio
async def test_reingest_with_enrichment_retiers_empty_row(db_session: AsyncSession) -> None:
    engine = MergeEngine(db_session)
    # 1) Unenriched ingest — no manifest/README, no commit_count → `empty`.
    n_bare = make_normalized(
        github_org="acme",
        github_repo="retier",
        display_name="retier",
        kind="mcp_server",
    )
    await engine.upsert(n_bare, raw_hash=_HASH_A, source="mcp_registry")
    await db_session.flush()
    item = (
        await db_session.execute(select(CatalogItem).where(CatalogItem.github_repo == "retier"))
    ).scalar_one()
    assert item.quality_tier == "empty"

    # 2) Re-crawl with enrichment (stars + commit_count proxy + manifest/README)
    #    → the row re-tiers and becomes catalog-visible.
    n_rich = make_normalized(
        github_org="acme",
        github_repo="retier",
        display_name="retier",
        kind="mcp_server",
        stars=120,
        metadata_files={"mcp.json": b"{}", "README.md": b"# x"},
        payload_hint={"commit_count": 64},
    )
    outcome = await engine.upsert(n_rich, raw_hash=_HASH_B, source="mcp_registry")
    assert outcome == "updated"
    await db_session.flush()
    await db_session.refresh(item)

    assert item.quality_tier in {"high", "medium"}
    assert item.quality_tier != "empty"
    assert item.github_stars == 120


@_ORM_BUG
@pytest.mark.asyncio
async def test_bare_update_never_downgrades_tiered_row(db_session: AsyncSession) -> None:
    """A signal-less update (no files, stars=None, no commit_count) must NOT
    recompute quality_tier — it would wrongly downgrade a tiered row to `empty`."""
    engine = MergeEngine(db_session)
    n_rich = make_normalized(
        github_org="acme",
        github_repo="keepme",
        display_name="keepme",
        kind="mcp_server",
        stars=200,
        metadata_files={"mcp.json": b"{}", "README.md": b"# x"},
        payload_hint={"commit_count": 80},
    )
    await engine.upsert(n_rich, raw_hash=_HASH_A, source="mcp_registry")
    await db_session.flush()
    item = (
        await db_session.execute(select(CatalogItem).where(CatalogItem.github_repo == "keepme"))
    ).scalar_one()
    assert item.quality_tier in {"high", "medium"}
    before = item.quality_tier

    # A bare aggregator update — explicitly no signals (stars=None).
    n_bare = NormalizedItem(
        github_org="acme",
        github_repo="keepme",
        display_name="keepme",
        kind="mcp_server",
        stars=None,
    )
    await engine.upsert(n_bare, raw_hash=_HASH_B, source="mcp_so")
    await db_session.flush()
    await db_session.refresh(item)
    assert item.quality_tier == before  # unchanged — no enrichment signals → no re-tier


# ---------------------------------------------------------------------------
# Tests: concurrent-insert race + deadlock resilience (DB log ERRORs in prod)
# ---------------------------------------------------------------------------


@_ORM_BUG
@pytest.mark.asyncio
async def test_upsert_slug_race_falls_through_to_update(db_session: AsyncSession) -> None:
    """Regression: aggregators crawl overlapping repos, so two concurrent cycles
    raced to INSERT the same capability slug — the loser hit `duplicate key …
    uq_catalog_items_slug`, which Postgres logs as an ERROR and which aborted its
    batch. `_insert_new` now uses INSERT … ON CONFLICT (slug) DO NOTHING (a clean
    no-op, never logged); a NULL returned id signals the conflict so the merger
    re-reads the peer's row and takes the UPDATE path.

    Simulated deterministically: the row already exists, but the pre-INSERT
    SELECT is forced to miss it once (the race window), so the INSERT hits the
    ON CONFLICT no-op and the merger recovers via re-read + update.
    """
    engine = MergeEngine(db_session)
    n = make_normalized(github_org="acme", github_repo="raced", display_name="cap")
    assert await engine.upsert(n, raw_hash=_HASH_A, source="github_topics") == "added"

    real_select = engine._select_by_slug  # pyright: ignore[reportPrivateUsage]
    calls = {"n": 0}

    async def flaky_select(slug: str) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # race: peer's row not visible to our SELECT yet
        return await real_select(slug)

    engine._select_by_slug = flaky_select  # type: ignore[method-assign]

    outcome = await engine.upsert(n, raw_hash=_HASH_B, source="github_topics")
    assert outcome == "updated"  # recovered via IntegrityError → re-read → update

    rows = (
        (await db_session.execute(select(CatalogItem).where(CatalogItem.github_repo == "raced")))
        .scalars()
        .all()
    )
    assert len(rows) == 1  # the failed INSERT was rolled back to the savepoint
    assert rows[0].content_hash_sha256 == _HASH_B  # the update was applied


@_ORM_BUG
@pytest.mark.asyncio
async def test_upsert_retries_on_deadlock(db_session: AsyncSession) -> None:
    """Regression: two batches inserting overlapping slugs in different order
    deadlocked on the unique index (`deadlock detected`), aborting a whole cycle.
    A deadlock (SQLSTATE 40P01) is now retried inside the upsert."""
    from sqlalchemy.exc import DBAPIError

    class _Deadlock(Exception):
        sqlstate = "40P01"

    engine = MergeEngine(db_session)
    n = make_normalized(github_org="acme", github_repo="deadlocked", display_name="cap")

    real_insert = engine._insert_new  # pyright: ignore[reportPrivateUsage]
    calls = {"n": 0}

    async def flaky_insert(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise DBAPIError("INSERT", {}, _Deadlock())  # first attempt deadlocks
        return await real_insert(*args, **kwargs)

    engine._insert_new = flaky_insert  # type: ignore[method-assign]

    outcome = await engine.upsert(n, raw_hash=_HASH_A, source="github_topics")
    assert outcome == "added"
    assert calls["n"] == 2  # retried once after the deadlock


def test_is_deadlock_detects_sqlstate_40p01() -> None:
    from sqlalchemy.exc import DBAPIError

    from app.ingestion.framework.merger import _is_deadlock  # pyright: ignore[reportPrivateUsage]

    class _Orig(Exception):
        sqlstate = "40P01"

    class _Other(Exception):
        sqlstate = "23505"  # unique_violation, not a deadlock

    assert _is_deadlock(DBAPIError("s", {}, _Orig())) is True
    assert _is_deadlock(DBAPIError("s", {}, _Other())) is False
