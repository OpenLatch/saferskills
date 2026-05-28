"""Commit a completed `ScanResult` to the database.

Two write paths:

- `persist_pending_scan` — called from POST /scans before the engine runs.
  Creates the `scans` row in `status=pending` with placeholder score values;
  this gives us a `scan_id` to return to the client before the work starts.
- `persist_completed_scan` — called from the queue worker after the engine
  returns. Updates the `scans` row with the real aggregate + sub-scores +
  score_breakdown, and bulk-inserts the `findings` rows.

CatalogItem creation/lookup: the scan engine submits a github_url; we
upsert a `catalog_items` row keyed on `(slug = "<org>--<repo>")` so subsequent
scans of the same repo update the same catalog entry.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog_item import CatalogItem
from app.models.scan import Finding, Scan
from app.scan.engine import ScanResult
from app.scan.fetch import GithubRef


def compute_idempotency_key(github_url: str, ref_sha: str, rubric_version: str) -> str:
    """SHA-256 idempotency key per scan-report.schema.json contract."""
    raw = f"{github_url}|{ref_sha}|{rubric_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def slug_for(ref: GithubRef) -> str:
    """`<org>--<repo>` URL-safe slug per I-02 D-15."""
    return f"{ref.org.lower()}--{ref.repo.lower()}"


def display_name_for(ref: GithubRef) -> str:
    """Human-readable display name for a fresh CatalogItem."""
    return ref.repo.replace("-", " ").replace("_", " ").title()


async def ensure_catalog_item(
    session: AsyncSession, ref: GithubRef, github_url: str
) -> CatalogItem:
    """Upsert a catalog_items row keyed on slug. Defaults are minimal — Phase B
    creates a stub entry; richer fields (popularity_score, sources, metadata)
    arrive with I-04 ingestion adapters.
    """
    slug = slug_for(ref)
    stmt = select(CatalogItem).where(CatalogItem.slug == slug)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    item = CatalogItem(
        kind="skill",
        slug=slug,
        display_name=display_name_for(ref),
        github_url=github_url,
        github_org=ref.org,
        github_repo=ref.repo,
        default_branch="main",
        popularity_tier="indexed",
        popularity_score=0,
        sources=[],
    )
    session.add(item)
    await session.flush()
    return item


def _placeholder_scan(
    catalog_item_id: UUID,
    idempotency_key: str,
    github_url: str,
    rubric_version: str,
    engine_version: str,
    source: str,
) -> Scan:
    """Initial scan row — the queue worker updates score columns on completion."""
    return Scan(
        catalog_item_id=catalog_item_id,
        idempotency_key=idempotency_key,
        github_url=github_url,
        ref_sha="0" * 40,
        aggregate_score=0,
        tier="unscoped",
        sub_scores={
            "security": 0,
            "supply_chain": 0,
            "maintenance": 0,
            "transparency": 0,
            "community": 0,
        },
        score_breakdown={"status": "pending"},
        rubric_version=rubric_version,
        engine_version=engine_version,
        latency_ms=0,
        source=source,
    )


async def persist_pending_scan(
    session: AsyncSession,
    *,
    catalog_item_id: UUID,
    idempotency_key: str,
    github_url: str,
    rubric_version: str,
    engine_version: str,
    source: str,
) -> Scan:
    """Insert the initial scans row + return it. Idempotent on idempotency_key."""
    existing_stmt = select(Scan).where(Scan.idempotency_key == idempotency_key)
    cached = (await session.execute(existing_stmt)).scalar_one_or_none()
    if cached is not None:
        return cached

    scan = _placeholder_scan(
        catalog_item_id=catalog_item_id,
        idempotency_key=idempotency_key,
        github_url=github_url,
        rubric_version=rubric_version,
        engine_version=engine_version,
        source=source,
    )
    session.add(scan)
    await session.flush()
    return scan


async def persist_completed_scan(
    session: AsyncSession,
    scan: Scan,
    result: ScanResult,
) -> Scan:
    """Update scan with score breakdown + bulk-insert findings."""
    scan.aggregate_score = result.aggregate_score
    scan.tier = result.tier
    scan.sub_scores = dict(result.sub_scores)
    scan.score_breakdown = dict(result.score_breakdown)
    scan.ref_sha = result.ref_sha
    scan.latency_ms = result.latency_ms

    if result.findings:
        await session.execute(
            pg_insert(Finding),
            [
                {
                    "scan_id": scan.id,
                    "rule_id": f.rule_id,
                    "severity": f.severity,
                    "sub_score": f.sub_score,
                    "penalty": f.penalty,
                    "status_at_scan": f.status_at_scan,
                    "file_path": f.file_path,
                    "line_start": f.line_start,
                    "line_end": f.line_end,
                    "matched_content_sha256": f.matched_content_sha256,
                    "remediation_link": f.remediation_link,
                    "rubric_version": f.rubric_version,
                }
                for f in result.findings
            ],
        )

    await session.flush()
    return scan


async def select_existing_by_idempotency(
    session: AsyncSession, idempotency_key: str
) -> Scan | None:
    stmt = select(Scan).where(Scan.idempotency_key == idempotency_key)
    return (await session.execute(stmt)).scalar_one_or_none()


def serialize_findings(findings: Iterable[Finding]) -> list[dict[str, object]]:
    """Slim public-API representation of finding rows for the report endpoint."""
    out: list[dict[str, object]] = []
    for f in findings:
        out.append(
            {
                "id": str(f.id),
                "rule_id": f.rule_id,
                "severity": f.severity,
                "sub_score": f.sub_score,
                "penalty": f.penalty,
                "status_at_scan": f.status_at_scan,
                "file_path": f.file_path,
                "line_start": f.line_start,
                "line_end": f.line_end,
                "matched_content_sha256": f.matched_content_sha256,
                "remediation_link": f.remediation_link,
                "rubric_version": f.rubric_version,
            }
        )
    return out
