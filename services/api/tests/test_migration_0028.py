"""Migration 0028 recomputes `latest_scan_*` for items whose latest scans tie.

Runs the migration's own statement inside the per-test SAVEPOINT, so it neither needs
a subprocess alembic nor leaves the DB off head.
"""

from __future__ import annotations

import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog_item import CatalogItem
from app.models.scan import Scan

_NOW = datetime(2026, 6, 28, tzinfo=UTC)
_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "2026_11_06_0028_latest_scan_tie_break.py"
)


def _migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0028", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _item(session: AsyncSession) -> CatalogItem:
    token = uuid.uuid4().hex[:8]
    item = CatalogItem(
        kind="plugin",
        slug=f"acme--{token}--plugin-{token}",
        display_name=token,
        github_url=f"https://github.com/acme/{token}",
        github_org="acme",
        github_repo=token,
        default_branch="main",
        popularity_tier="indexed",
        popularity_score=1,
        agent_compatibility=[],
        sources=[],
    )
    session.add(item)
    await session.flush()
    return item


async def _scan(
    session: AsyncSession, item: CatalogItem, *, score: int, tier: str, scan_id: UUID
) -> Scan:
    scan = Scan(
        id=scan_id,
        catalog_item_id=item.id,
        idempotency_key=uuid.uuid4().hex,
        github_url=item.github_url,
        ref_sha="0" * 40,
        aggregate_score=score,
        tier=tier,
        sub_scores={},
        score_breakdown={},
        rubric_version="r",
        engine_version="e",
        latency_ms=0,
        source="ingestion",
        scanned_at=_NOW,
    )
    session.add(scan)
    await session.flush()
    return scan


async def _point_at(session: AsyncSession, item: CatalogItem, scan: Scan) -> None:
    await session.execute(
        sa.update(CatalogItem)
        .where(CatalogItem.id == item.id)
        .values(
            latest_scan_id=scan.id,
            latest_scan_score=scan.aggregate_score,
            latest_scan_tier=scan.tier,
            latest_scanned_at=scan.scanned_at,
        )
    )


async def _latest(session: AsyncSession, item: CatalogItem) -> tuple[object, ...]:
    row = await session.execute(
        sa.text(
            "SELECT latest_scan_id, latest_scan_score, latest_scan_tier "
            "FROM catalog_items WHERE id = :id"
        ),
        {"id": item.id},
    )
    return tuple(row.one())


@pytest.mark.asyncio
async def test_0028_moves_a_tied_item_to_its_lower_score(db_session: AsyncSession) -> None:
    tied = await _item(db_session)
    red = await _scan(db_session, tied, score=15, tier="red", scan_id=UUID(int=1))
    green = await _scan(db_session, tied, score=91, tier="green", scan_id=UUID(int=2))
    await _point_at(db_session, tied, green)

    single = await _item(db_session)
    only = await _scan(db_session, single, score=70, tier="yellow", scan_id=uuid.uuid4())
    await _point_at(db_session, single, only)

    await db_session.execute(_migration().RETIE_SQL)

    assert await _latest(db_session, tied) == (red.id, 15, "red")
    assert await _latest(db_session, single) == (only.id, 70, "yellow")
