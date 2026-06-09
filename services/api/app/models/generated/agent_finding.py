# DO NOT EDIT — regenerate via: pnpm run generate (scripts/generate_sqlalchemy_models.py)
"""AgentFinding SQLAlchemy model — maps to the `agent_findings` table."""

from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.generated._base import Base, agent_test_verdict_enum, severity_enum


class AgentFinding(Base):
    """One observed-vulnerable behavioral test on an agent scan (an `agent_findings` row). Findings rows are..."""

    __tablename__ = "agent_findings"

    __table_args__ = (sa.Index("idx_agent_findings_run_id", "agent_run_id"),)

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    )

    agent_run_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    test_id: Mapped[str] = mapped_column(
        sa.String(8),
        nullable=False,
    )

    severity: Mapped[str] = mapped_column(
        severity_enum,
        nullable=False,
    )

    verdict: Mapped[str] = mapped_column(
        agent_test_verdict_enum,
        nullable=False,
    )

    family: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
    )

    owasp_refs: Mapped[list[Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        server_default=sa.text("'[]'::jsonb"),
    )

    atlas_refs: Mapped[list[Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        server_default=sa.text("'[]'::jsonb"),
    )

    nist_refs: Mapped[list[Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        server_default=sa.text("'[]'::jsonb"),
    )

    score_delta: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    )

    detection_rule: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
    )

    leaked_canary_slot: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    def __repr__(self) -> str:
        return f"AgentFinding(id={self.id!r})"
