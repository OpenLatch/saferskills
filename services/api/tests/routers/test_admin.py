"""Admin endpoints — auth gate + mutations + audit log."""

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
async def test_force_cycle_api_source_queues(db_client: AsyncClient) -> None:
    # An `api` source (npm) has a registered `ingest_cycle_npm` task → force-cycle
    # must enqueue exactly one job on the (in-memory) queue and 200.
    from procrastinate.testing import InMemoryConnector

    from app.ingestion import procrastinate_app

    conn = InMemoryConnector()
    with procrastinate_app.replace_connector(conn):
        await conn.open_async()
        resp = await db_client.post("/api/v1/admin/sources/npm/force-cycle", headers=_HDR)
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "queued": True}
        assert [j["task_name"] for j in conn.jobs.values()] == ["ingest_cycle_npm"]


@pytest.mark.asyncio
async def test_admin_force_cycle_webhook_400(db_client: AsyncClient) -> None:
    # github_skills is a webhook source (no cadence → no `ingest_cycle_*` task).
    # Regression: even with a live queue it must 400 and enqueue NOTHING — never
    # silently 200-queue an orphan job no worker ever runs (allow_unknown=False).
    # The message is reworded from the old "not schedulable (disabled or non-api)"
    # to an accurate webhook/disabled explanation (Fix 1).
    from procrastinate.testing import InMemoryConnector

    from app.ingestion import procrastinate_app

    conn = InMemoryConnector()
    with procrastinate_app.replace_connector(conn):
        await conn.open_async()
        resp = await db_client.post("/api/v1/admin/sources/github_skills/force-cycle", headers=_HDR)
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "no periodic cycle" in detail
        assert "webhook" in detail
        assert "not schedulable" not in detail  # the misleading old message is gone
        assert conn.jobs == {}  # no orphan job leaked onto the queue


@pytest.mark.asyncio
async def test_admin_force_cycle_already_enqueued_409(db_client: AsyncClient) -> None:
    # A cadenced source whose `ingest_cycle_*` cycle is already queued (holds the
    # per-source `queueing_lock`) must return 409 "already queued or running" — NOT
    # the old broad-except 400 "not schedulable" (which mislabelled a busy source as
    # unschedulable, the dashboard's "3 failed" after a force-cycle ALL). Regression:
    # force-cycle npm twice on the same queue; the second hits the held lock.
    from procrastinate.testing import InMemoryConnector

    from app.ingestion import procrastinate_app

    conn = InMemoryConnector()
    with procrastinate_app.replace_connector(conn):
        await conn.open_async()
        first = await db_client.post("/api/v1/admin/sources/npm/force-cycle", headers=_HDR)
        assert first.status_code == 200  # the cycle is now queued (holds the lock)

        second = await db_client.post("/api/v1/admin/sources/npm/force-cycle", headers=_HDR)
        assert second.status_code == 409
        detail = second.json()["detail"]
        assert "already queued or running" in detail
        assert "not schedulable" not in detail
        # Exactly one job on the queue — the second defer was rejected, no duplicate.
        assert [j["task_name"] for j in conn.jobs.values()] == ["ingest_cycle_npm"]


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


# ─── Keyless local-dev exemption ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_local_dev_no_key_allowed(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ENV=development + no configured key → keyless read access (no header)."""
    monkeypatch.setattr(get_settings(), "saferskills_admin_key", None)
    monkeypatch.setattr(get_settings(), "env", "development")
    resp = await db_client.get("/api/v1/admin/sources")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) >= 14


@pytest.mark.asyncio
async def test_local_dev_no_key_mutation_audits_local_dev(
    db_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A keyless local-dev mutation succeeds and audits as `local-dev`."""
    monkeypatch.setattr(get_settings(), "saferskills_admin_key", None)
    monkeypatch.setattr(get_settings(), "env", "development")
    item = _item()
    db_session.add(item)
    await db_session.commit()

    resp = await db_client.post(
        f"/api/v1/admin/catalog/{item.slug}/archive", json={"reason": "spam"}
    )
    assert resp.status_code == 200

    row = (
        (
            await db_session.execute(
                select(AdminAuditLog)
                .where(AdminAuditLog.target == item.slug)
                .order_by(AdminAuditLog.ts.desc())
            )
        )
        .scalars()
        .first()
    )
    assert row is not None
    assert row.actor_admin_key_fp == "local-dev"


@pytest.mark.asyncio
@pytest.mark.parametrize("env", ["staging", "production"])
async def test_no_key_off_development_403(
    db_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    """Exemption must not apply off ENV=development — still 403 with no key."""
    monkeypatch.setattr(get_settings(), "saferskills_admin_key", None)
    monkeypatch.setattr(get_settings(), "env", env)
    resp = await db_client.get("/api/v1/admin/sources")
    assert resp.status_code == 403
