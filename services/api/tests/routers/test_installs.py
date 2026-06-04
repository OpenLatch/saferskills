"""Tests for POST /api/v1/installs + the real install_activity aggregate (D-05-31).

Covers the happy path (report → 204 → item-detail shows real GROUP-BY counts),
adversarial input (unknown slug → 404, bad enum → 422), and the IP-redaction
contract (a raw IP is never stored).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access_log_middleware import redact_ip
from app.models.catalog_item import CatalogItem
from app.models.install_event import InstallEvent
from app.models.scan import Scan


@pytest.mark.asyncio
async def test_report_install_then_aggregate(
    db_client: AsyncClient,
    db_session: AsyncSession,
    seed_item: tuple[CatalogItem, Scan],
) -> None:
    item, _scan = seed_item

    for agent in ("claude-code", "claude-code", "cursor"):
        resp = await db_client.post(
            "/api/v1/installs",
            json={"slug": item.slug, "agent": agent, "kind": "mcp_server", "cli_version": "0.1.0"},
        )
        assert resp.status_code == 204, resp.text

    # The item-detail surface now reflects real counts (no mock).
    detail = await db_client.get(f"/api/v1/items/{item.slug}")
    assert detail.status_code == 200
    activity = detail.json()["install_activity"]
    assert activity["all_time"] == 3
    assert activity["this_week"] == 3
    dist = {row["agent"]: row["percentage"] for row in activity["agent_distribution"]}
    assert dist["claude-code"] == 67  # 2/3
    assert dist["cursor"] == 33  # 1/3

    # One row per report, redacted IP only (never a raw address).
    rows = (
        (
            await db_session.execute(
                select(InstallEvent).where(InstallEvent.catalog_item_id == item.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 3
    assert all(
        "/" not in (r.redacted_ip or "") for r in rows
    )  # network address, no CIDR slash leak


@pytest.mark.asyncio
async def test_report_install_unknown_slug_404(db_client: AsyncClient) -> None:
    resp = await db_client.post(
        "/api/v1/installs",
        json={"slug": "does--not-exist", "agent": "claude-code", "kind": "skill"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_report_install_bad_agent_422(
    db_client: AsyncClient, seed_item: tuple[CatalogItem, Scan]
) -> None:
    item, _ = seed_item
    resp = await db_client.post(
        "/api/v1/installs",
        json={"slug": item.slug, "agent": "codex-cli", "kind": "mcp_server"},
    )
    assert (
        resp.status_code == 422
    )  # legacy alias is canonicalized CLI-side, not accepted on the wire


@pytest.mark.asyncio
async def test_no_installs_returns_zeroed_activity(
    db_client: AsyncClient, seed_item: tuple[CatalogItem, Scan]
) -> None:
    item, _ = seed_item
    detail = await db_client.get(f"/api/v1/items/{item.slug}")
    activity = detail.json()["install_activity"]
    assert activity == {
        "this_week": 0,
        "this_month": 0,
        "all_time": 0,
        "agent_distribution": [],
    }


def test_redact_ip_contract() -> None:
    # Locks the privacy.md write-time redaction the installs router relies on.
    assert redact_ip("203.0.113.42") == "203.0.113.0"
    assert redact_ip("2001:db8:85a3::8a2e:370:7334") == "2001:db8:85a3::"
    assert redact_ip(None) is None
