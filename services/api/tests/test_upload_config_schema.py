"""Config parsing + schema-relaxation guards for I-3.5 (§13.13 / §13.14)."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import Settings
from app.schemas.catalog_summary import CatalogItemDetail
from app.schemas.scan_run import ScanRunReportDetail

_SCHEMAS = Path(__file__).resolve().parents[3] / "schemas"


def test_allowed_extensions_parse_from_csv_env() -> None:
    s = Settings(upload_allowed_extensions="md, .JSON ,zip")  # type: ignore[arg-type]
    assert s.upload_allowed_extensions == [".md", ".json", ".zip"]


def test_upload_config_defaults() -> None:
    s = Settings()
    assert s.upload_max_bytes == 10_485_760
    assert s.private_lookup_daily_limit == 60
    assert s.unlisted_retention_days == 90
    assert s.sweep_interval_seconds == 3600


def test_scan_run_report_dto_accepts_null_github() -> None:
    dto = ScanRunReportDetail.model_validate(
        {
            "id": "x",
            "github_url": None,
            "repo_aggregate_score": 80,
            "repo_tier": "green",
            "kind_tally": {"skill": 1},
            "capability_count": 1,
            "capabilities": [],
            "scanned_at": "2026-06-02T00:00:00Z",
            "rubric_version": "abc1234",
            "engine_version": "def5678",
            "latency_ms": 10,
            "source": "submission",
            "status": "completed",
            "visibility": "unlisted",
            "source_kind": "upload",
            "artifact_sha256": "a" * 64,
            "uploaded_filename": "SKILL.md",
            "share_url": "http://x/scans/r/tok",
        }
    )
    assert dto.github_url is None and dto.source_kind == "upload"


def test_catalog_detail_dto_accepts_upload_shape() -> None:
    dto = CatalogItemDetail.model_validate(
        {
            "id": "x",
            "slug": "upload--a7b3c4d5--skill-pdf",
            "kind": "skill",
            "display_name": "pdf",
            "github_url": None,
            "github_org": None,
            "github_repo": None,
            "popularity_tier": "on_demand",
            "popularity_score": 0,
            "findings_count": 0,
            "registries": ["upload"],
            "agent_compatibility": ["claude-code"],
            "updated_at": "2026-06-02T00:00:00Z",
            "sources": [{"registryId": "upload", "registryUrl": "http://x/scans/abc"}],
        }
    )
    assert dto.github_org is None and dto.sources[0]["registryId"] == "upload"


def test_json_schemas_relaxed_and_upload_enum() -> None:
    run_report = json.loads((_SCHEMAS / "scan-run-report.schema.json").read_text())
    assert "githubUrl" not in run_report["required"]
    for f in ("visibility", "sourceKind", "artifactSha256", "shareUrl"):
        assert f in run_report["properties"]

    summary = json.loads((_SCHEMAS / "scan-report-summary.schema.json").read_text())
    assert "githubUrl" not in summary["required"]
    assert "shareUrl" not in summary["properties"]  # never in list payloads

    catalog = json.loads((_SCHEMAS / "catalog-item.schema.json").read_text())
    assert "githubOrg" not in catalog["required"]
    registry_enum = catalog["properties"]["sources"]["items"]["properties"]["registryId"]["enum"]
    assert "upload" in registry_enum
