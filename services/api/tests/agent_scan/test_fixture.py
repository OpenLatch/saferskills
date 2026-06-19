"""The committed fixture (`fixtures/agent-scan-report.sample.json`) must stay
a valid agent-scan report. We round-trip each projection through the WIRE DTO
(`AgentScanReportDetail.model_validate`) — the same shape the report endpoints emit
— so a schema/DTO drift fails here, not silently in the frontend (the
generated Zod is a `z.unknown()` placeholder and validates anything)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.schemas.agent_scan import AgentScanReportDetail

_FIXTURE = Path(__file__).resolve().parents[4] / "fixtures" / "agent-scan-report.sample.json"


def _load() -> dict[str, object]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("projection", ["red_public", "red_private", "green_pass"])
def test_fixture_projection_round_trips(projection: str) -> None:
    report = AgentScanReportDetail.model_validate(_load()[projection])
    # Re-dump (by_alias=False → snake_case) and re-validate to lock the wire shape.
    AgentScanReportDetail.model_validate(report.model_dump(by_alias=False))


def test_public_projection_has_no_transcript() -> None:
    """The public projection NEVER carries a transcript window (route-driven split)."""
    report = AgentScanReportDetail.model_validate(_load()["red_public"])
    assert all(f.evidence_excerpt is None for f in report.findings)


def test_private_projection_hydrates_evidence() -> None:
    """The unlisted (token-route) projection DOES carry the redacted transcript."""
    report = AgentScanReportDetail.model_validate(_load()["red_private"])
    assert any(f.evidence_excerpt is not None for f in report.findings)


def test_green_pass_is_clean_ship() -> None:
    report = AgentScanReportDetail.model_validate(_load()["green_pass"])
    assert report.band == "green"
    assert report.findings == []
