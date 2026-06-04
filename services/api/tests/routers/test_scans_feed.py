"""GET /scans feed excludes the bulk auto-scan firehose (ingestion + rescan_rules)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scan_run import ScanRun


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
