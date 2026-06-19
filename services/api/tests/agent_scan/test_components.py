"""Component-score projection: a linked component `scan_run`'s
per-capability `scans` become the Agent Report's Component Scores rows; the unlisted
deep-link points every row at the run report; a null link is an honest empty tab.

Also pins the two pure helpers feeding the dossier icons: the bootstrap DTO's
`_normalize_kind_tally` (folds `mcp_server` -> `mcp`) and the directory's
`_capability_tally` (reads the stored tally).
"""

from __future__ import annotations

import secrets

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_scan.components import load_component_scores
from app.agent_scan.directory import _capability_tally  # pyright: ignore[reportPrivateUsage]
from app.core.config import get_settings
from app.models.generated.agent_run import AgentRun
from app.models.generated.catalog_item import CatalogItem
from app.models.generated.scan import Scan
from app.models.generated.scan_run import ScanRun
from app.schemas.agent_scan import _normalize_kind_tally  # pyright: ignore[reportPrivateUsage]

# ── pure helpers (no DB) ────────────────────────────────────────────────────────


def test_normalize_kind_tally_folds_mcp_server_and_drops_unknown() -> None:
    out = _normalize_kind_tally({"mcp_server": 2, "mcp": 1, "skill": 3, "bogus": 9, "hook": -4})
    # mcp_server folds into mcp (2+1); unknown key dropped; negative clamped to 0.
    assert out == {"mcp": 3, "skill": 3, "hook": 0}


def test_normalize_kind_tally_handles_non_dict_and_empty() -> None:
    assert _normalize_kind_tally(None) is None
    assert _normalize_kind_tally("nope") is None
    assert _normalize_kind_tally({}) is None
    assert _normalize_kind_tally({"bogus": 1}) is None


def test_capability_tally_reads_stored_tally() -> None:
    tally = _capability_tally({"skill": 3, "mcp": 1, "hook": 2})
    assert (tally.skill, tally.mcp, tally.hook, tally.plugin, tally.rules) == (3, 1, 2, 0, 0)
    # NULL/absent -> all-zero (no icons).
    zero = _capability_tally(None)
    assert (zero.skill, zero.mcp, zero.hook, zero.plugin, zero.rules) == (0, 0, 0, 0, 0)


# ── DB-backed projection ────────────────────────────────────────────────────────


def _agent_run(*, visibility: str, component_scan_run_id: object | None) -> AgentRun:
    return AgentRun(
        status="published",
        agent_name="acme-agent",
        runtime="claude-code",
        band="green",
        pack_id="p",
        pack_version="v",
        visibility=visibility,
        rubric_version="r",
        engine_version="e",
        latency_ms=0,
        idempotency_key="ar-" + secrets.token_hex(6),
        nonce="n",
        share_token=(secrets.token_hex(8) if visibility == "unlisted" else None),
        component_scan_run_id=component_scan_run_id,
    )


def _scan_run(*, visibility: str, share_token: str | None) -> ScanRun:
    return ScanRun(
        rubric_version="r",
        engine_version="e",
        source="submission",
        status="completed",
        visibility=visibility,
        source_kind="upload",
        share_token=share_token,
        idempotency_key="cr-" + secrets.token_hex(6),
    )


def _item(*, kind: str, name: str) -> CatalogItem:
    suffix = secrets.token_hex(4)
    return CatalogItem(
        kind=kind,
        slug=f"acme--repo-{suffix}--{kind}-{name}",
        display_name=name,
        popularity_tier="indexed",
    )


def _scan(*, item_id: object, run_id: object, score: int, tier: str, path: str) -> Scan:
    return Scan(
        catalog_item_id=item_id,
        idempotency_key="sc-" + secrets.token_hex(6),
        aggregate_score=score,
        tier=tier,
        sub_scores={"security": score},
        score_breakdown={},
        rubric_version="r",
        engine_version="e",
        latency_ms=1,
        source="submission",
        scan_run_id=run_id,
        component_path=path,
    )


@pytest.mark.asyncio
async def test_public_link_maps_scans_to_rows(db_session: AsyncSession) -> None:
    scan_run = _scan_run(visibility="public", share_token=None)
    skill = _item(kind="skill", name="pdf-extract")
    mcp = _item(kind="mcp_server", name="payments")
    db_session.add_all([scan_run, skill, mcp])
    await db_session.flush()
    db_session.add_all(
        [
            _scan(item_id=skill.id, run_id=scan_run.id, score=82, tier="green", path="skills/pdf"),
            _scan(item_id=mcp.id, run_id=scan_run.id, score=47, tier="orange", path="servers/pay"),
        ]
    )
    run = _agent_run(visibility="public", component_scan_run_id=scan_run.id)
    db_session.add(run)
    await db_session.flush()

    rows, url = await load_component_scores(db_session, run, get_settings(), private=False)
    assert url is None  # public -> rows link to their real /items/<slug>
    # Sorted mcp -> skill, then score.
    assert [r["kind"] for r in rows] == ["mcp_server", "skill"]
    mcp_row = rows[0]
    assert mcp_row["name"] == "payments"
    assert mcp_row["score"] == 47
    assert mcp_row["tier"] == "orange"
    assert mcp_row["path"] == "servers/pay"
    assert mcp_row["slug"] == mcp.slug


@pytest.mark.asyncio
async def test_unlisted_link_points_rows_at_run_report(db_session: AsyncSession) -> None:
    token = secrets.token_hex(10)
    scan_run = _scan_run(visibility="unlisted", share_token=token)
    skill = _item(kind="skill", name="pdf-extract")
    db_session.add_all([scan_run, skill])
    await db_session.flush()
    db_session.add(_scan(item_id=skill.id, run_id=scan_run.id, score=90, tier="green", path="s/p"))
    run = _agent_run(visibility="unlisted", component_scan_run_id=scan_run.id)
    db_session.add(run)
    await db_session.flush()

    rows, url = await load_component_scores(db_session, run, get_settings(), private=True)
    base = get_settings().public_base_url.rstrip("/")
    assert url == f"{base}/scans/r/{token}"
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_null_link_yields_empty_tab(db_session: AsyncSession) -> None:
    run = _agent_run(visibility="public", component_scan_run_id=None)
    db_session.add(run)
    await db_session.flush()
    rows, url = await load_component_scores(db_session, run, get_settings(), private=False)
    assert rows == []
    assert url is None
