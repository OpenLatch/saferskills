"""Company-level telemetry capture (I-5.5, AE-9). Redact-then-derive, opt-out,
closed-key fingerprint (no host fields), EU gate predicate."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.agent_scan import asn, telemetry
from app.agent_scan.grading import GradeOutcome
from app.models.agent_scan_telemetry import AgentScanTelemetry
from app.models.generated.agent_run import AgentRun
from app.schemas.agent_scan import AgentScanResultV1


def _request(ip: str) -> Request:
    return Request({"type": "http", "headers": [], "client": (ip, 4444)})


def _result() -> AgentScanResultV1:
    return AgentScanResultV1(
        schema_version="agent_scan_result.v1",
        run_id="r",
        pack_id="p",
        pack_version="v",
        capabilities_present=["agent_response"],
        capabilities_absent=["mcp"],
        tests=[],
    )


def _outcome() -> GradeOutcome:
    return GradeOutcome(
        findings=[],
        checks=[],
        score=100,
        band="green",
        score_breakdown={},
        confidence="high",
        trust_labels=[],
        verdict_label="Ship",
        cap_callout="",
        family_tally={},
    )


async def _run(db_session: AsyncSession) -> AgentRun:
    run = AgentRun(
        status="published",
        agent_name="a",
        runtime="claude-code",
        band="green",
        pack_id="p",
        pack_version="v",
        visibility="public",
        rubric_version="r",
        engine_version="e",
        latency_ms=1,
        idempotency_key="tk-" + __import__("secrets").token_hex(6),
        nonce="n",
    )
    db_session.add(run)
    await db_session.flush()
    return run


@pytest.mark.asyncio
async def test_redact_then_derive_passes_network_base(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, str | None] = {}

    def _fake_resolve(ip: str | None) -> asn.AsnRecord:
        seen["ip"] = ip
        return {"asn": "AS13335", "as_org": "Cloudflare", "country": "US"}

    monkeypatch.setattr(asn, "resolve", _fake_resolve)
    run = await _run(db_session)
    await telemetry.capture(
        db_session,
        run=run,
        result=_result(),
        outcome=_outcome(),
        request=_request("203.0.113.77"),
        opted_out=False,
    )
    # The raw .77 host is NEVER passed to resolve — only the /24 network base.
    assert seen["ip"] == "203.0.113.0"


@pytest.mark.asyncio
async def test_normal_capture_writes_closed_key_fingerprint(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake_resolve(ip: str | None) -> asn.AsnRecord:
        return {"asn": "AS1", "as_org": "x", "country": "FR"}

    monkeypatch.setattr(asn, "resolve", _fake_resolve)
    run = await _run(db_session)
    await telemetry.capture(
        db_session,
        run=run,
        result=_result(),
        outcome=_outcome(),
        request=_request("198.51.100.5"),
        opted_out=False,
    )
    row = (
        await db_session.execute(
            select(AgentScanTelemetry).where(AgentScanTelemetry.agent_run_id == run.id)
        )
    ).scalar_one()
    assert row.opted_out is False
    assert row.asn == "AS1"
    assert row.fingerprint is not None
    assert set(row.fingerprint) <= {
        "runtime",
        "capabilities_present",
        "capabilities_absent",
        "observed_band",
        "critical_count",
        "high_count",
    }
    # No host identity ever captured.
    assert "username" not in row.fingerprint
    assert "machine_name" not in row.fingerprint


@pytest.mark.asyncio
async def test_opt_out_writes_minimal_row(db_session: AsyncSession) -> None:
    run = await _run(db_session)
    await telemetry.capture(
        db_session,
        run=run,
        result=_result(),
        outcome=_outcome(),
        request=_request("203.0.113.1"),
        opted_out=True,
    )
    row = (
        await db_session.execute(
            select(AgentScanTelemetry).where(AgentScanTelemetry.agent_run_id == run.id)
        )
    ).scalar_one()
    assert row.opted_out is True
    assert row.asn is None
    assert row.fingerprint is None
