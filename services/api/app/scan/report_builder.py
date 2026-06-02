"""Project ORM rows → the `ScanReportDetail` wire DTO.

Shared by `routers/scans.py` (GET /scans/<id>) and `routers/items.py`
(GET /items/<slug> → `latest_scan`) so the report shape stays identical across
the scan-report and item-detail surfaces. A scan that still holds placeholder
score values (aggregate 0 + no findings) is reported as `running`; everything
else is `completed`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from app.models.catalog_item import CatalogItem
from app.models.scan import Finding, Scan
from app.models.scan_run import ScanRun
from app.schemas.scan_run import CapabilityRow, FindingsSummary, ScanRunReportDetail
from app.schemas.scan_submit import ScanReportDetail

ScanStatus = Literal["pending", "running", "completed", "failed"]


def derive_scan_status(scan: Scan, findings: Sequence[Finding]) -> ScanStatus:
    """A pending placeholder scan (score 0, no findings) is still running."""
    if scan.aggregate_score == 0 and not findings:
        return "running"
    return "completed"


def _finding_dict(f: Finding) -> dict[str, object]:
    return {
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


def _findings_summary(findings: Sequence[Finding]) -> FindingsSummary:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in findings:
        if f.severity in counts:
            counts[f.severity] += 1
    return FindingsSummary(**counts, total=len(findings))


def build_scan_report_detail(
    scan: Scan, item: CatalogItem, findings: Sequence[Finding]
) -> ScanReportDetail:
    """Build the full `ScanReportDetail` DTO for a scan + its catalog item."""
    return ScanReportDetail.model_validate(
        {
            "id": str(scan.id),
            "github_url": scan.github_url,
            "slug": item.slug,
            "display_name": item.display_name,
            "aggregate_score": scan.aggregate_score,
            "tier": scan.tier,
            "sub_scores": scan.sub_scores,
            "score_breakdown": scan.score_breakdown,
            "findings": [
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
                for f in findings
            ],
            "scanned_at": scan.scanned_at,
            "rubric_version": scan.rubric_version,
            "engine_version": scan.engine_version,
            "latency_ms": scan.latency_ms,
            "source": scan.source,
            "status": derive_scan_status(scan, findings),
            "ref_sha": scan.ref_sha,
            "component_path": scan.component_path,
            "scan_run_id": str(scan.scan_run_id) if scan.scan_run_id is not None else None,
        }
    )


def build_scan_run_report(
    run: ScanRun,
    capabilities: Sequence[tuple[Scan, CatalogItem, Sequence[Finding]]],
    *,
    share_url: str | None = None,
) -> ScanRunReportDetail:
    """Build the repo-scan report DTO: rollup + one `CapabilityRow` per scan.

    `capabilities` is `(scan, catalog_item, findings)` per discovered capability,
    ordered by the caller (kind then name). The item-detail report
    (`build_scan_report_detail`) is unchanged — it reuses each capability's scan.

    `share_url` is supplied ONLY by the unlisted `/scans/r/<token>` route — it is
    never set when the report is served from a public surface (the field stays a
    detail-only contract, never in a list payload).
    """
    rows = [
        CapabilityRow(
            kind=item.kind,  # type: ignore[arg-type]
            name=item.display_name,
            component_path=scan.component_path,
            aggregate_score=scan.aggregate_score,
            tier=scan.tier,  # type: ignore[arg-type]
            scan_id=str(scan.id),
            catalog_slug=item.slug,
            sub_scores=dict(scan.sub_scores),
            findings_summary=_findings_summary(findings),
            findings=[_finding_dict(f) for f in findings],  # type: ignore[arg-type]
        )
        for scan, item, findings in capabilities
    ]
    return ScanRunReportDetail.model_validate(
        {
            "id": str(run.id),
            "github_url": run.github_url,
            "repo_aggregate_score": run.repo_aggregate_score,
            "repo_tier": run.repo_tier,
            "kind_tally": dict(run.kind_tally),
            "capability_count": run.capability_count,
            "capabilities": rows,
            "scanned_at": run.scanned_at,
            "rubric_version": run.rubric_version,
            "engine_version": run.engine_version,
            "latency_ms": run.latency_ms,
            "source": run.source,
            "status": run.status,
            "ref_sha": run.ref_sha,
            "visibility": run.visibility,
            "source_kind": run.source_kind,
            "artifact_sha256": run.content_hash_sha256,
            "uploaded_filename": run.original_filename,
            "expires_at": run.expires_at,
            "share_url": share_url,
        }
    )
