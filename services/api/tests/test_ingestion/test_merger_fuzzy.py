"""PostgreSQL regressions for bounded, index-backed fuzzy candidate selection."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import TextClause

from app.ingestion.framework.merger import MergeEngine
from app.models import CatalogItem, MergeCandidate
from tests.test_ingestion.conftest import make_normalized


@pytest.mark.asyncio
async def test_fuzzy_prefilter_preserves_strict_threshold_and_archived_exclusion(
    db_session: AsyncSession,
) -> None:
    engine = MergeEngine(db_session)
    ids: dict[str, UUID] = {}
    for name in ("a b c", "a b c d", "a b c d e", "a b c d e f", "A B C"):
        ids[name] = await engine._insert_staging_row(  # pyright: ignore[reportPrivateUsage]
            make_normalized(github_org=None, github_repo=None, display_name=name), "npm"
        )
    await db_session.execute(
        update(CatalogItem).where(CatalogItem.id == ids["A B C"]).values(archived=True)
    )
    # All supersets pass token_set_ratio, so PostgreSQL must do the filtering.
    # Preserve the original bound float comparison even at the 0.6 boundary:
    # similarity() returns real, while SQLAlchemy binds a Python float as float8.
    assert (
        await db_session.execute(text("SELECT similarity('a b c', 'a b c d e') = 0.6::real"))
    ).scalar_one()
    expected = set(
        (
            await db_session.execute(
                text(
                    "SELECT id FROM catalog_items "
                    "WHERE similarity(display_name, :name) > :pre AND archived = false"
                ).bindparams(name="a b c", pre=0.6)
            )
        ).scalars()
    )
    # A connection's previous setting must not suppress valid 0.75 matches.
    await db_session.execute(text("SET LOCAL pg_trgm.similarity_threshold = 0.95"))

    outcome = await engine.upsert(
        make_normalized(github_org=None, github_repo=None, display_name="a b c"),
        raw_hash="a" * 64,
        source="mcp_registry",
    )

    assert outcome == "added_with_merge_candidate"
    candidates = (await db_session.execute(select(MergeCandidate))).scalars().all()
    existing_ids = set(ids.values())
    matched = {
        item_id
        for candidate in candidates
        for item_id in (candidate.left_artifact_id, candidate.right_artifact_id)
        if item_id in existing_ids
    }
    assert matched == expected
    assert ids["a b c d"] in matched
    assert ids["a b c d e f"] not in matched
    assert ids["A B C"] not in matched


@pytest.mark.asyncio
async def test_fuzzy_prefilter_ranks_before_twenty_candidate_limit(
    db_session: AsyncSession,
) -> None:
    engine = MergeEngine(db_session)
    # These 21 early rows are all reasonable matches, but the exact match
    # inserted last must take priority over them within the bounded shortlist.
    for index in range(21):
        await engine._insert_staging_row(  # pyright: ignore[reportPrivateUsage]
            make_normalized(
                github_org=None,
                github_repo=None,
                display_name=f"super mcp server {index}",
            ),
            "npm",
        )
    exact_id = await engine._insert_staging_row(  # pyright: ignore[reportPrivateUsage]
        make_normalized(github_org=None, github_repo=None, display_name="super mcp server"),
        "npm",
    )

    await engine.upsert(
        make_normalized(github_org=None, github_repo=None, display_name="super mcp server"),
        raw_hash="a" * 64,
        source="mcp_registry",
    )

    candidates = (await db_session.execute(select(MergeCandidate))).scalars().all()
    assert len(candidates) == 20
    assert any(
        exact_id in (candidate.left_artifact_id, candidate.right_artifact_id)
        for candidate in candidates
    )


@pytest.mark.asyncio
async def test_fuzzy_prefilter_can_use_existing_trigram_index(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Enough unrelated rows for the trigram index to beat the partial indexes
    # that also cover archived=false; all rows roll back with this fixture.
    await db_session.execute(
        text(
            "INSERT INTO catalog_items (kind, slug, display_name, popularity_tier) "
            "SELECT 'skill', 'fuzzy-plan-' || i, md5(i::text), 'indexed' "
            "FROM generate_series(1, 5000) AS i"
        )
    )
    await db_session.execute(text("SELECT gin_clean_pending_list('idx_catalog_items_name_trgm')"))
    await db_session.execute(text("ANALYZE catalog_items"))
    statements: list[TextClause] = []
    execute = db_session.execute

    async def record_query(statement: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(statement, TextClause) and str(statement).startswith(
            "SELECT id, display_name FROM catalog_items"
        ):
            statements.append(statement)
        return await execute(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", record_query)
    await MergeEngine(db_session).upsert(
        make_normalized(github_org=None, github_repo=None, display_name="super mcp server"),
        raw_hash="a" * 64,
        source="mcp_registry",
    )
    assert len(statements) == 1
    # Tiny isolated fixtures normally favour a sequential scan. Disabling it
    # proves that the ACTUAL executed query can use the production GIN index,
    # without depending on catalog cardinality or machine-specific timings.
    await execute(text("SET LOCAL enable_seqscan = off"))
    query = statements[0]
    plan = (
        await execute(text(f"EXPLAIN (FORMAT JSON) {query}").bindparams(**query.compile().params))
    ).scalar_one()
    assert "idx_catalog_items_name_trgm" in json.dumps(plan)


@pytest.mark.asyncio
async def test_fuzzy_similarity_setting_is_transaction_local(db_session: AsyncSession) -> None:
    # Load pg_trgm before reading its GUC (the extension is lazily loaded).
    await db_session.execute(text("SELECT similarity('a', 'a')"))
    before = (await db_session.execute(text("SHOW pg_trgm.similarity_threshold"))).scalar_one()
    await MergeEngine(db_session).upsert(
        make_normalized(github_org=None, github_repo=None, display_name="threshold isolation"),
        raw_hash="a" * 64,
        source="mcp_registry",
    )
    assert (
        await db_session.execute(text("SHOW pg_trgm.similarity_threshold"))
    ).scalar_one() == "0.6"

    await db_session.rollback()

    assert (
        await db_session.execute(text("SHOW pg_trgm.similarity_threshold"))
    ).scalar_one() == before
