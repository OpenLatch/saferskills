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
from app.schemas.scan_submit import ScanReportDetail

ScanStatus = Literal["pending", "running", "completed", "failed"]


def derive_scan_status(scan: Scan, findings: Sequence[Finding]) -> ScanStatus:
    """A pending placeholder scan (score 0, no findings) is still running."""
    if scan.aggregate_score == 0 and not findings:
        return "running"
    return "completed"


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
        }
    )
