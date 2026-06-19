"""Wire type for POST /api/v1/installs — opt-in install telemetry.

The install CLI reports a successful install (only when the user opted in) so the
catalog's `install_activity` reflects real adoption instead of the old mock.
Closed-enum agent + kind, no PII; the submitter IP is redacted to /24 (v4) or
/48 (v6) at write time in the router (privacy.md). Hand-written endpoint DTO —
`install_events` is an internal store with no JSON-Schema entity.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.orm_base import OrmBaseModel
from app.services.agent_compat import AgentName

# The 5-kind artifact taxonomy (mirrors the native `kind` PG enum / KIND_VALUES).
KindName = Literal["skill", "mcp_server", "hook", "plugin", "rules"]


class InstallReportRequest(OrmBaseModel):
    """One reported install: which capability, which agent, which kind."""

    slug: str = Field(..., min_length=1, max_length=255)
    agent: AgentName
    kind: KindName
    cli_version: str | None = Field(default=None, max_length=32)
