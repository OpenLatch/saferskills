"""Source-local registry identity must survive re-crawls and concurrent arrivals."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.ingestion.framework.base_adapter import NormalizedItem
from app.ingestion.framework.merger import MergeEngine
from app.models import CatalogItem, ItemSource, MergeCandidate


def _listing(identity: str | None = "alice/test-skill") -> NormalizedItem:
    return NormalizedItem(
        github_org=None,
        github_repo=None,
        display_name="Registry skill",
        description="First description",
        kind="skill",
        registry_item_id=identity,
        source_url="https://clawhub.ai/alice/test-skill",
    )


async def test_registry_recrawl_refreshes_one_staged_item(db_session: AsyncSession) -> None:
    engine = MergeEngine(db_session)
    n = _listing()
    assert await engine.upsert(n, raw_hash="a" * 64, source="clawhub") == "added"
    first = (await db_session.execute(select(CatalogItem))).scalar_one()
    assert first.item_metadata is not None
    assert first.item_metadata["description"] == n.description
    assert first.content_hash_sha256 == "a" * 64
    assert first.quality_tier == "low"

    outcome = await engine.upsert(
        replace(n, display_name="Renamed registry skill", description="Updated description"),
        raw_hash="b" * 64,
        source="clawhub",
    )

    assert outcome == "updated"
    await db_session.flush()
    item = (await db_session.execute(select(CatalogItem))).scalar_one()
    assert item.item_metadata is not None
    assert item.id == first.id
    assert item.display_name == "Renamed registry skill"
    assert item.item_metadata["description"] == "Updated description"
    assert item.item_metadata["conflicts"] == []
    assert item.item_metadata["pending_merge"] is True
    assert item.content_hash_sha256 == "b" * 64
    assert item.quality_tier == "low"
    source = (await db_session.execute(select(ItemSource))).scalar_one()
    assert source.catalog_item_id == item.id
    assert source.registry_url == n.source_url
    assert not (await db_session.execute(select(MergeCandidate))).scalars().all()


async def test_registry_identity_is_scoped_to_source_and_owner(db_session: AsyncSession) -> None:
    engine = MergeEngine(db_session)
    for source, identity in (
        ("clawhub", "alice/test-skill"),
        ("clawhub", "bob/test-skill"),
        ("npm", "alice/test-skill"),
    ):
        await engine.upsert(_listing(identity), raw_hash="a" * 64, source=source)

    items = (await db_session.execute(select(CatalogItem))).scalars().all()
    assert len(items) == 3
    assert len({item.slug for item in items}) == 3
    candidates = (await db_session.execute(select(MergeCandidate))).scalars().all()
    assert len(candidates) == 3
    assert all(c.left_artifact_id != c.right_artifact_id for c in candidates)


async def test_shared_source_url_without_explicit_identity_stays_separate(
    db_session: AsyncSession,
) -> None:
    engine = MergeEngine(db_session)
    # MCP Registry currently uses its root URL for every item. Never infer a
    # unique identity from source_url or a display name shared by two entries.
    n = replace(_listing(None), source_url="https://registry.modelcontextprotocol.io")
    await engine.upsert(n, raw_hash="a" * 64, source="mcp_registry")
    await engine.upsert(n, raw_hash="a" * 64, source="mcp_registry")
    assert len((await db_session.execute(select(CatalogItem))).scalars().all()) == 2


async def test_registry_identity_does_not_override_canonical_github_metadata(
    db_session: AsyncSession,
) -> None:
    engine = MergeEngine(db_session)
    n = replace(
        _listing(),
        github_org="acme",
        github_repo="skill",
        github_url="https://github.com/acme/skill",
    )
    await engine.upsert(n, raw_hash="a" * 64, source="github_topics")
    assert (
        await engine.upsert(
            replace(n, description="Registry description"), raw_hash="b" * 64, source="clawhub"
        )
        == "updated"
    )
    item = (await db_session.execute(select(CatalogItem))).scalar_one()
    assert item.item_metadata is not None
    assert item.item_metadata["description"] == "First description"
    assert not item.slug.startswith("pending--")
    assert item.item_metadata["conflicts"][-1]["chosen"] == "current"


async def test_concurrent_registry_arrivals_create_one_item(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    unique = uuid4().hex
    n = replace(_listing(f"alice/{unique}"), display_name=f"concurrent registry {unique}")
    barrier = asyncio.Barrier(2)

    async def arrive() -> str:
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            engine = MergeEngine(session)
            select_by_slug = engine._select_by_slug  # pyright: ignore[reportPrivateUsage]
            first_lookup = True

            async def synchronized_lookup(slug: str) -> CatalogItem | None:
                nonlocal first_lookup
                item = await select_by_slug(slug)
                if first_lookup:
                    first_lookup = False
                    assert item is None
                    # Both transactions observe absence before either inserts.
                    await barrier.wait()
                return item

            monkeypatch.setattr(engine, "_select_by_slug", synchronized_lookup)
            outcome = await engine.upsert(n, raw_hash="a" * 64, source="clawhub")
            await session.commit()
            return outcome

    try:
        async with asyncio.TaskGroup() as group:
            async with asyncio.timeout(15):
                first = group.create_task(arrive())
                second = group.create_task(arrive())
                await asyncio.gather(first, second)
        assert sorted([first.result(), second.result()]) == ["added", "updated"]
        async with AsyncSession(db_engine) as session:
            item = (
                await session.execute(
                    select(CatalogItem).where(CatalogItem.display_name == n.display_name)
                )
            ).scalar_one()
            assert (
                len(
                    (
                        await session.execute(
                            select(ItemSource).where(ItemSource.catalog_item_id == item.id)
                        )
                    )
                    .scalars()
                    .all()
                )
                == 1
            )
            assert (
                not (
                    await session.execute(
                        select(MergeCandidate).where(
                            (MergeCandidate.left_artifact_id == item.id)
                            | (MergeCandidate.right_artifact_id == item.id)
                        )
                    )
                )
                .scalars()
                .all()
            )
    finally:
        async with AsyncSession(db_engine) as session:
            await session.execute(
                delete(CatalogItem).where(CatalogItem.display_name == n.display_name)
            )
            await session.commit()
