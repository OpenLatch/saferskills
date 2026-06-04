"""Eagle-eye `GET /admin/sources` enrichment + `…/{source}/runs` drill-down."""

from __future__ import annotations

import datetime as dt

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import IngestionRun

_KEY = "testkey-abc"
_HDR = {"X-Admin-Key": _KEY}


@pytest.fixture(autouse=True)
def _set_admin_key(  # pyright: ignore[reportUnusedFunction]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "saferskills_admin_key", _KEY)


def _run(
    source: str, *, status: str = "succeeded", minutes_ago: int = 1, **over: object
) -> IngestionRun:
    now = dt.datetime.now(tz=dt.UTC)
    fields: dict[str, object] = {
        "source": source,
        "trigger": "scheduled",
        "status": status,
        "started_at": now - dt.timedelta(minutes=minutes_ago),
        "ended_at": now - dt.timedelta(minutes=minutes_ago),
        "duration_ms": 1200,
        "items_seen": 10,
        "items_added": 3,
        "items_updated": 2,
        "http_304_count": 5,
        "http_5xx_count": 0,
        "attempt": 1,
    }
    fields.update(over)
    return IngestionRun(**fields)


@pytest.mark.asyncio
async def test_sources_enriched_shape(db_client: AsyncClient) -> None:
    resp = await db_client.get("/api/v1/admin/sources", headers=_HDR)
    assert resp.status_code == 200
    body = resp.json()
    assert "generated_at" in body
    summary = body["summary"]
    assert {"overall", "total", "by_status", "critical_count", "warn_count"} <= set(summary)
    assert summary["overall"] in {"healthy", "degraded", "critical"}
    assert isinstance(body["critical"], list)
    first = body["data"][0]
    # additive: original fields preserved + new nested objects present
    assert {"source", "status", "kind", "enabled", "cadence"} <= set(first)
    assert {"live", "last_run", "schedule", "health"} <= set(first)
    assert first["health"]["status"] in (
        "disabled",
        "blocked",
        "paused",
        "running",
        "never_run",
        "failing",
        "overdue",
        "healthy",
    )


@pytest.mark.asyncio
async def test_sources_reflects_last_run(db_client: AsyncClient, db_session: AsyncSession) -> None:
    db_session.add(_run("npm", status="succeeded", items_added=7))
    await db_session.commit()

    resp = await db_client.get("/api/v1/admin/sources", headers=_HDR)
    assert resp.status_code == 200
    npm = next(p for p in resp.json()["data"] if p["source"] == "npm")
    assert npm["last_run"] is not None
    assert npm["last_run"]["status"] == "succeeded"
    assert npm["last_run"]["items_added"] == 7


@pytest.mark.asyncio
async def test_runs_pagination(db_client: AsyncClient, db_session: AsyncSession) -> None:
    db_session.add(_run("pypi", minutes_ago=1))
    db_session.add(_run("pypi", minutes_ago=2))
    db_session.add(_run("pypi", minutes_ago=3))
    await db_session.commit()

    page1 = (
        await db_client.get("/api/v1/admin/sources/pypi/runs", headers=_HDR, params={"limit": 2})
    ).json()
    assert len(page1["data"]) == 2
    assert page1["next_before"] is not None
    # newest-first
    assert page1["data"][0]["started_at"] > page1["data"][1]["started_at"]

    page2 = (
        await db_client.get(
            "/api/v1/admin/sources/pypi/runs",
            headers=_HDR,
            params={"limit": 2, "before": page1["next_before"]},
        )
    ).json()
    assert len(page2["data"]) == 1
    assert page2["next_before"] is None


@pytest.mark.asyncio
async def test_runs_unknown_source_404(db_client: AsyncClient) -> None:
    resp = await db_client.get("/api/v1/admin/sources/nope/runs", headers=_HDR)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_runs_empty_source_ok(db_client: AsyncClient) -> None:
    resp = await db_client.get("/api/v1/admin/sources/glama/runs", headers=_HDR)
    assert resp.status_code == 200
    assert resp.json() == {"data": [], "next_before": None}


@pytest.mark.asyncio
async def test_runs_requires_admin_key(db_client: AsyncClient) -> None:
    assert (await db_client.get("/api/v1/admin/sources/npm/runs")).status_code == 403
