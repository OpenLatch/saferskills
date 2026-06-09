"""AgentEvidence — internal raw-record store for one agent scan (I-5.5).

Hand-written internal store (no JSON-Schema source, no wire DTO — never serialized
over the API). Holds the submitted `agent_scan_result.v1` (`result_json`) AND the
exact served signed pack bytes (`pack_bytes`) for reproducibility. Per-run, NO
dedup (mirrors `upload_files`). The PUBLIC report route MUST NEVER load this row
(it carries the private transcript); only the grader + the unlisted token route
read it. See `.claude/rules/database.md` § Agent scan + `security.md`
§ Scan-trace transparency.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AgentEvidence(Base):
    __tablename__ = "agent_evidence"

    agent_run_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # The submitted `agent_scan_result.v1` raw evidence (turns + recorded mock-tool
    # args). NULL until the client submits. NEVER a scan-trace field.
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # The EXACT served signed pack bytes — archived so the pack re-verifies later.
    pack_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return f"AgentEvidence(agent_run_id={self.agent_run_id!r})"
