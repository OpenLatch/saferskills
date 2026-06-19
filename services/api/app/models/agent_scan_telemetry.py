"""AgentScanTelemetry — write-only company-level signal for one agent scan.

Hand-written internal store (no JSON-Schema source, no wire DTO). WRITE-ONLY for
now (the reader ships later; mirrors `access_log`). Stores ONLY the derived ASN /
as_org / country and a server-derived closed-key fingerprint — NEVER a raw IP, a
slug, or any PII (IP is redacted-then-derived at write time). `agent_run_id` is
`SET NULL` so deleting a run keeps the anonymous aggregate. See
`.claude/rules/privacy.md` + `security.md` § Vendor-data isolation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AgentScanTelemetry(Base):
    __tablename__ = "agent_scan_telemetry"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    agent_run_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    asn: Mapped[str | None] = mapped_column(String(16), nullable=True)
    as_org: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    fingerprint: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    opted_out: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return f"AgentScanTelemetry(id={self.id!r})"
