"""Admin endpoints (I-04 Phase C) — auth gate + mutations + audit log."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import AdminAuditLog, CatalogItem

_KEY = "testkey-abc"
_HDR = {"X-Admin-Key": _KEY}


@pytest.fixture(autouse=True)
def _set_admin_key(  # pyright: ignore[reportUnusedFunction]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "saferskills_admin_key", _KEY)


def _item(**over: Any) -> CatalogItem:
    now = dt.datetime.now(tz=dt.UTC)
    suffix = uuid.uuid4().hex[:8]
    fields: dict[str, Any] = {
        "kind": "mcp_server",
        "slug": f"acme--admin-{suffix}",
        "display_name": f"admin-{suffix}",
        "github_url": f"https://github.com/acme/admin-{suffix}",
        "github_org": "acme",
        "github_repo": f"admin-{suffix}",
        "default_branch": "main",
        "popularity_tier": "indexed",
        "popularity_score": 10,
        "popularity_rank_tier": "long_tail",
        "agent_compatibility": ["claude-code"],
        "quality_tier": "high",
        "quality_signals": {},
        "kind_signals": {"has_mcp_json": True},
        "availability": "available",
        "archived": False,
        "source_kind": "github",
        "visibility": "public",
        "consecutive404_count": 0,
        "popularity_breakdown": {},
        "sources": [
            {
                "registryId": "github_topics",
                "registryUrl": "",
                "firstIndexedAt": now.isoformat(),
                "lastSeenAt": now.isoformat(),
            }
        ],
        "item_metadata": {"description": "x"},
        "created_at": now,
        "updated_at": now,
    }
    fields.update(over)
    return CatalogItem(**fields)


@pytest.mark.asyncio
async def test_403_without_key(db_client: AsyncClient) -> None:
    resp = await db_client.get("/api/v1/admin/sources")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_403_wrong_key(db_client: AsyncClient) -> None:
    resp = await db_client.get("/api/v1/admin/sources", headers={"X-Admin-Key": "nope"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_sources_list(db_client: AsyncClient) -> None:
    resp = await db_client.get("/api/v1/admin/sources", headers=_HDR)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) >= 14
    assert {"source", "status", "kind", "enabled"} <= set(data[0])


@pytest.mark.asyncio
async def test_pause_unpause_writes_audit(db_client: AsyncClient, db_session: AsyncSession) -> None:
    before = (await db_session.execute(select(func.count(AdminAuditLog.id)))).scalar_one()

    resp = await db_client.post(
        "/api/v1/admin/sources/npm/pause",
        headers=_HDR,
        json={"reason": "test", "contact": "a@b.c"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"]["status"] == "paused"

    after = (await db_session.execute(select(func.count(AdminAuditLog.id)))).scalar_one()
    assert after == before + 1

    resp2 = await db_client.post("/api/v1/admin/sources/npm/unpause", headers=_HDR)
    assert resp2.status_code == 200
    assert resp2.json()["status"]["status"] == "active"


@pytest.mark.asyncio
async def test_pause_unknown_source_404(db_client: AsyncClient) -> None:
    resp = await db_client.post("/api/v1/admin/sources/nope/pause", headers=_HDR, json={})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_re_classify(db_client: AsyncClient, db_session: AsyncSession) -> None:
    item = _item()
    db_session.add(item)
    await db_session.commit()
    resp = await db_client.post(f"/api/v1/admin/catalog/{item.slug}/re-classify", headers=_HDR)
    assert resp.status_code == 200
    body = resp.json()
    assert "before" in body and "after" in body


@pytest.mark.asyncio
async def test_archive_then_unarchive(db_client: AsyncClient, db_session: AsyncSession) -> None:
    item = _item()
    db_session.add(item)
    await db_session.commit()

    resp = await db_client.post(
        f"/api/v1/admin/catalog/{item.slug}/archive", headers=_HDR, json={"reason": "spam"}
    )
    assert resp.status_code == 200
    await db_session.refresh(item)
    assert item.archived is True
    assert item.availability == "archived"

    resp2 = await db_client.post(f"/api/v1/admin/catalog/{item.slug}/un-archive", headers=_HDR)
    assert resp2.status_code == 200
    await db_session.refresh(item)
    assert item.archived is False
    assert item.availability == "available"


@pytest.mark.asyncio
async def test_popularity_top_n(db_client: AsyncClient, db_session: AsyncSession) -> None:
    db_session.add(_item(popularity_score=99))
    await db_session.commit()
    resp = await db_client.get("/api/v1/admin/popularity/top-n", headers=_HDR, params={"n": 10})
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)


@pytest.mark.asyncio
async def test_merge_candidates_list_empty(db_client: AsyncClient) -> None:
    resp = await db_client.get("/api/v1/admin/merge-candidates", headers=_HDR)
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)
