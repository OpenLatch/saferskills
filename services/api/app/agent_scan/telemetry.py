"""Company-level agent-scan telemetry capture (I-5.5, D-5.5-08/16).

Write-only at I-5.5 (reader -> I-06, mirrors `access_log`). Stores ONLY a derived
ASN / org / country + a server-derived closed-key fingerprint - NEVER a raw IP, a
slug, or any PII. Redact-then-derive: the submitter IP is redacted to the `/24`
(v4) / `/48` (v6) network base FIRST, and only that base is passed to the ASN
lookup, so no raw IP is ever read or stored (privacy.md). Best-effort - the caller
wraps this in try/except so a telemetry failure never breaks the scan.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_scan import asn
from app.agent_scan.grading import GradeOutcome
from app.core.access_log_middleware import redact_ip
from app.core.config import get_settings
from app.models.agent_scan_telemetry import AgentScanTelemetry
from app.models.generated.agent_run import AgentRun
from app.routers.scans import rate_limit_ip
from app.schemas.agent_scan import AgentScanResultV1

# NOTE: at I-5.5 the EU gate is a deliberate no-op — the anonymous baseline
# (asn/org/country + closed-key fingerprint) is stored for EVERY region; aggressive
# enrichment is an I-06 reader concern (plan §6, "not built here"). The country
# code is recorded so the I-06 reader can apply the EEA/UK/CH minimal-enrichment
# gate; the predicate itself lands with that reader, not here.


def _fingerprint(run: AgentRun, result: AgentScanResultV1, outcome: GradeOutcome) -> dict[str, Any]:
    """Closed-key, server-derived only - built from the submission + the grade.
    Structurally cannot carry username / machine-name / domain (never collected)."""
    return {
        "runtime": run.runtime,
        "capabilities_present": list(result.capabilities_present),
        "capabilities_absent": list(result.capabilities_absent),
        "observed_band": run.band,
        "critical_count": sum(1 for f in outcome.findings if f.severity == "critical"),
        "high_count": sum(1 for f in outcome.findings if f.severity == "high"),
    }


async def capture(
    session: AsyncSession,
    *,
    run: AgentRun,
    result: AgentScanResultV1,
    outcome: GradeOutcome,
    request: Request,
    opted_out: bool,
) -> None:
    """Write one `agent_scan_telemetry` row (commits its own work)."""
    if opted_out:
        session.add(AgentScanTelemetry(agent_run_id=run.id, opted_out=True))
        await session.commit()
        return

    ip = rate_limit_ip(request, get_settings())
    redacted = redact_ip(ip)  # "/24" or "/48" network - never the raw IP
    lookup_base = redacted.split("/", 1)[0] if redacted else None
    geo = asn.resolve(lookup_base)

    session.add(
        AgentScanTelemetry(
            agent_run_id=run.id,
            asn=geo["asn"],
            as_org=geo["as_org"][:255] if geo["as_org"] else None,
            country=geo["country"],
            fingerprint=_fingerprint(run, result, outcome),
            opted_out=False,
        )
    )
    await session.commit()
