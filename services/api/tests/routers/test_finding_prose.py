"""Inline finding prose on the report builders (D-05-32 reversed).

Pins that both report chokepoints fold the generated rule-content prose onto each
finding (`title`/`explanation`/`category_label`/`severity_rationale`/`remediation`),
and that a finding whose rule_id has no content entry degrades to all-None while
still carrying `rule_id` + `remediation_link`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog_item import CatalogItem
from app.models.scan import Finding, Scan
from app.scan.report_builder import build_scan_report_detail, build_scan_run_report
from app.services.rule_prose import lookup

# Seeded finding rule_id — present in app/generated/rule_content.json.
_KNOWN_RULE = "SS-MCP-POISON-UNICODE-TAG-01"


def _fake_run() -> SimpleNamespace:
    """An in-memory stand-in for a ScanRun (the builder only reads attributes)."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        github_url="https://github.com/acme/widget",
        repo_aggregate_score=87,
        repo_tier="green",
        kind_tally={"mcp_server": 1},
        capability_count=1,
        scanned_at=datetime.now(tz=UTC),
        rubric_version="abc1234",
        engine_version="def5678",
        latency_ms=2400,
        source="submission",
        status="completed",
        ref_sha="a" * 40,
        visibility="public",
        source_kind="github",
        content_hash_sha256=None,
        original_filename=None,
        expires_at=None,
    )


@pytest.mark.asyncio
async def test_item_detail_builder_inlines_prose(
    seed_item: tuple[CatalogItem, Scan], db_session: AsyncSession
) -> None:
    item, scan = seed_item
    findings = list((await db_session.execute(_findings_stmt(scan.id))).scalars().all())
    report = build_scan_report_detail(scan, item, findings)

    f = report.findings[0]
    prose = lookup(_KNOWN_RULE)
    assert prose is not None
    assert f.title == prose.title
    assert f.explanation == prose.explanation
    assert f.category_label == prose.category_label
    assert f.remediation is not None
    assert f.remediation.action == prose.remediation.action


@pytest.mark.asyncio
async def test_run_builder_inlines_prose(
    seed_item: tuple[CatalogItem, Scan], db_session: AsyncSession
) -> None:
    item, scan = seed_item
    findings = list((await db_session.execute(_findings_stmt(scan.id))).scalars().all())
    run = _fake_run()
    report = build_scan_run_report(run, [(scan, item, findings)])  # type: ignore[arg-type]

    f = report.capabilities[0].findings[0]
    assert f.title is not None
    assert f.remediation is not None


@pytest.mark.asyncio
async def test_unknown_rule_degrades_to_none(
    seed_item: tuple[CatalogItem, Scan], db_session: AsyncSession
) -> None:
    item, scan = seed_item
    bogus = Finding(
        scan_id=scan.id,
        rule_id="SS-MCP-NOT-A-REAL-RULE-99",
        severity="low",
        sub_score="security",
        penalty=1,
        status_at_scan="active",
        file_path="server.py",
        line_start=1,
        line_end=1,
        matched_content_sha256="0" * 64,
        remediation_link="https://example.com/fix",
        rubric_version="abc1234",
    )
    db_session.add(bogus)
    await db_session.flush()

    report = build_scan_report_detail(scan, item, [bogus])
    f = report.findings[0]
    assert f.rule_id == "SS-MCP-NOT-A-REAL-RULE-99"
    assert f.remediation_link == "https://example.com/fix"
    assert f.title is None
    assert f.explanation is None
    assert f.category_label is None
    assert f.severity_rationale is None
    assert f.remediation is None


def _findings_stmt(scan_id: object):
    from sqlalchemy import select

    return select(Finding).where(Finding.scan_id == scan_id)
