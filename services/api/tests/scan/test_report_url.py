"""Regression: the run-report DTO carries a webapp-origin `report_url`.

The CLI (and any client) must be able to link to the real report page without
knowing the webapp origin — which differs from the API origin in local dev
(API :8000 vs webapp :4321). Before this, `report_url` was absent and the CLI
fell back to `<api_origin>/scans/<id>`, which 404s (the API has no such route).

The builder reads only attributes, so a `SimpleNamespace` stands in for the ORM
`ScanRun` — no DB needed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

from app.core.config import get_settings
from app.models.scan_run import ScanRun
from app.scan.report_builder import build_scan_run_report

_RUN_ID = uuid.UUID("1516693a-d5b0-4000-a4fd-31074895a41b")


def _run() -> ScanRun:
    # The builder reads only attributes, so a SimpleNamespace stands in for the
    # ORM ScanRun (no DB needed); cast it for the type-checker.
    ns = SimpleNamespace(
        id=_RUN_ID,
        github_url="https://github.com/acme/kit",
        repo_aggregate_score=98,
        repo_tier="green",
        kind_tally={"skill": 1},
        capability_count=1,
        scanned_at=datetime(2026, 6, 8, tzinfo=UTC),
        rubric_version="v3",
        engine_version="e1",
        latency_ms=1200,
        source="submission",
        status="completed",
        ref_sha="b" * 40,
        visibility="public",
        source_kind="github",
        content_hash_sha256=None,
        original_filename=None,
        expires_at=None,
    )
    return cast(ScanRun, ns)


def test_public_run_report_url_is_webapp_origin_not_api() -> None:
    report = build_scan_run_report(_run(), [])
    public_base = get_settings().public_base_url.rstrip("/")
    assert report.report_url == f"{public_base}/scans/{_RUN_ID}"
    assert report.report_url is not None
    # The public report page, never the unlisted token route.
    assert "/scans/r/" not in report.report_url
    # The webapp origin is the public base, not the API's own origin.
    assert report.report_url.endswith(f"/scans/{_RUN_ID}")


def test_unlisted_run_report_url_reuses_share_token_url() -> None:
    # An unlisted run is reachable only via its token URL — the public
    # `/scans/<id>` page 404s it — so `report_url` mirrors `share_url`.
    token_url = "http://localhost:4321/scans/r/SOME_TOKEN"
    report = build_scan_run_report(_run(), [], share_url=token_url)
    assert report.report_url == token_url
    assert report.share_url == token_url
