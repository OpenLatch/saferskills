"""GET /scans feed excludes the bulk auto-scan firehose (ingestion + rescan_rules)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog_item import CatalogItem
from app.models.scan import Finding, Scan
from app.models.scan_run import ScanRun
from tests.sql_capture import capture_sql


def _run(source: str, *, org: str) -> ScanRun:
    return ScanRun(
        idempotency_key=uuid.uuid4().hex,
        github_url=f"https://github.com/{org}/repo",
        ref_sha=None,
        repo_aggregate_score=80,
        repo_tier="green",
        kind_tally={"skill": 1},
        capability_count=1,
        rubric_version="abc1234",
        engine_version="def5678",
        source=source,
        latency_ms=10,
        file_count=1,
        status="completed",
        visibility="public",
        source_kind="github",
    )


@pytest.mark.asyncio
async def test_feed_excludes_ingestion_and_rescan_rules(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    db_session.add_all(
        [
            _run("submission", org="sub"),
            _run("ingestion", org="ing"),
            _run("rescan_rules", org="rules"),
            _run("rescan_drift", org="drift"),
        ]
    )
    await db_session.flush()

    resp = await db_client.get("/api/v1/scans")
    assert resp.status_code == 200
    body = resp.json()
    sources = {row["github_url"] for row in body["data"]}

    assert "https://github.com/sub/repo" in sources
    assert "https://github.com/drift/repo" in sources
    assert "https://github.com/ing/repo" not in sources
    assert "https://github.com/rules/repo" not in sources
    # total_count also reflects the exclusion (only submission + drift).
    assert body["total_count"] == 2


@pytest.mark.asyncio
async def test_feed_counts_findings_for_the_page_only(
    db_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Regression: the feed grouped all findings x scans before applying LIMIT, so
    every request aggregated the whole findings table."""
    run = _run("submission", org="counted")
    db_session.add(run)
    await db_session.flush()
    item = CatalogItem(
        kind="skill",
        slug=f"counted--{uuid.uuid4().hex[:8]}",
        display_name="Counted",
        github_url="https://github.com/counted/repo",
        github_org="counted",
        github_repo="repo",
        default_branch="main",
        popularity_tier="indexed",
        popularity_score=1,
        agent_compatibility=[],
        sources=[],
    )
    db_session.add(item)
    await db_session.flush()
    scan = Scan(
        catalog_item_id=item.id,
        scan_run_id=run.id,
        idempotency_key=uuid.uuid4().hex,
        github_url=run.github_url,
        ref_sha="0" * 40,
        aggregate_score=80,
        tier="green",
        sub_scores={},
        score_breakdown={},
        rubric_version="abc1234",
        engine_version="def5678",
        latency_ms=0,
        source="submission",
    )
    db_session.add(scan)
    await db_session.flush()
    for line in (1, 2):
        db_session.add(
            Finding(
                scan_id=scan.id,
                rule_id="SS-SKILL-INJECT-FENCED-RUN-02",
                severity="low",
                sub_score="security",
                penalty=1,
                status_at_scan="active",
                file_path="SKILL.md",
                line_start=line,
                line_end=line,
                matched_content_sha256="0" * 64,
                remediation_link="https://saferskills.ai/methodology",
                rubric_version="abc1234",
            )
        )
    await db_session.flush()

    async with capture_sql(db_session) as statements:
        resp = await db_client.get("/api/v1/scans", params={"limit": 100})

    assert resp.status_code == 200
    row = next(r for r in resp.json()["data"] if r["id"] == str(run.id))
    assert row["findings_count"] == 2
    grouped = [s for s in statements if "findings" in s and "GROUP BY" in s]
    assert grouped
    assert all("scan_run_id IN" in s for s in grouped), grouped
