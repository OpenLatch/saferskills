"""Integration test: StubAdapter.run_cycle adds catalog_items + ingestion_events.

NOTE: All tests here currently xfail due to the same ORM column name mismatch
documented in test_merger.py (consecutive404_count vs consecutive_404_count).
The StubAdapter.run_cycle → MergeEngine.upsert → CatalogItem INSERT path hits
this bug during the first SELECT for an existing row.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.ingestion.config.loader import SourceConfig
from app.ingestion.sources.stub import StubAdapter
from app.models import CatalogItem, IngestionEvent, ItemSource
from tests.test_ingestion.conftest import SAMPLE_REPO


def _ORM_BUG(fn: Any) -> Any:
    # ORM column-name bug fixed (migration + merger aligned to generated
    # column names); marker kept as a no-op so existing decorators stay valid.
    return fn


def _make_stub_config(items: list[dict[str, Any]]) -> SourceConfig:
    """Build a SourceConfig that StubAdapter accepts."""
    return SourceConfig(
        name="github_topics",
        kind="api",
        hosts=["api.github.com", "raw.githubusercontent.com"],
        discovery={"items": items},
    )


@_ORM_BUG
@pytest.mark.asyncio
async def test_stub_cycle_adds_catalog_items(db_session: AsyncSession) -> None:
    config = _make_stub_config([SAMPLE_REPO])
    adapter = StubAdapter(config)
    counters = await adapter.run_cycle(db_session, get_settings())

    assert counters["items_added"] >= 1

    rows = (await db_session.execute(select(CatalogItem))).scalars().all()
    assert any(r.github_org == "testorg" for r in rows)


@_ORM_BUG
@pytest.mark.asyncio
async def test_stub_cycle_ingestion_events_have_applied_at(db_session: AsyncSession) -> None:
    config = _make_stub_config([SAMPLE_REPO])
    adapter = StubAdapter(config)
    await adapter.run_cycle(db_session, get_settings())

    rows = (await db_session.execute(select(IngestionEvent))).scalars().all()
    assert len(rows) >= 1
    # All events from run_cycle should be marked applied
    for row in rows:
        assert row.applied_at is not None, f"Event {row.id} has applied_at=None"


@_ORM_BUG
@pytest.mark.asyncio
async def test_stub_cycle_item_has_correct_source_kind_and_visibility(
    db_session: AsyncSession,
) -> None:
    config = _make_stub_config([SAMPLE_REPO])
    adapter = StubAdapter(config)
    await adapter.run_cycle(db_session, get_settings())

    rows = (await db_session.execute(select(CatalogItem))).scalars().all()
    for row in rows:
        assert row.source_kind == "github", f"Expected github, got {row.source_kind}"
        assert row.visibility == "public", f"Expected public, got {row.visibility}"


@_ORM_BUG
@pytest.mark.asyncio
async def test_stub_cycle_item_has_item_source_row(db_session: AsyncSession) -> None:
    config = _make_stub_config([SAMPLE_REPO])
    adapter = StubAdapter(config)
    await adapter.run_cycle(db_session, get_settings())

    items = (await db_session.execute(select(CatalogItem))).scalars().all()
    assert len(items) >= 1

    for item in items:
        src = (
            await db_session.execute(
                select(ItemSource).where(ItemSource.catalog_item_id == item.id)
            )
        ).scalar_one_or_none()
        assert src is not None, f"No ItemSource for catalog_item {item.id}"


@_ORM_BUG
@pytest.mark.asyncio
async def test_stub_cycle_multiple_items(db_session: AsyncSession) -> None:
    import copy

    repo2 = copy.deepcopy(SAMPLE_REPO)
    repo2["name"] = "second-skill"
    repo2["full_name"] = "testorg/second-skill"
    repo2["owner"] = {"login": "testorg2", "type": "Organization"}

    config = _make_stub_config([SAMPLE_REPO, repo2])
    adapter = StubAdapter(config)
    counters = await adapter.run_cycle(db_session, get_settings())

    assert counters["items_added"] == 2

    rows = (await db_session.execute(select(CatalogItem))).scalars().all()
    assert len(rows) >= 2


@_ORM_BUG
@pytest.mark.asyncio
async def test_stub_cycle_second_run_updates_not_adds(db_session: AsyncSession) -> None:
    """A second run_cycle with the same item should update, not add again."""
    config = _make_stub_config([SAMPLE_REPO])
    adapter = StubAdapter(config)

    c1 = await adapter.run_cycle(db_session, get_settings())
    assert c1["items_added"] == 1

    c2 = await adapter.run_cycle(db_session, get_settings())
    assert c2["items_added"] == 0
    assert c2["items_updated"] >= 1
