# DO NOT EDIT — regenerate via: pnpm run generate (scripts/generate_sqlalchemy_models.py)
"""AgentRun SQLAlchemy model — maps to the `agent_runs` table."""

from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.generated._base import Base, agent_run_status_enum, tier_enum, visibility_enum


class AgentRun(Base):
    """Full report for one agent scan (an `agent_runs` row): the run state machine + the behavioral-score wire..."""

    __tablename__ = "agent_runs"

    __table_args__ = (
        sa.Index(
            "idx_agent_runs_expires_at",
            "expires_at",
            postgresql_where=sa.text("visibility = 'unlisted'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    )

    status: Mapped[str] = mapped_column(
        agent_run_status_enum,
        nullable=False,
        server_default=sa.text("'created'"),
    )

    agent_name: Mapped[str] = mapped_column(
        sa.String(200),
        nullable=False,
    )

    runtime: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
    )

    score: Mapped[int | None] = mapped_column(
        sa.Integer,
        nullable=True,
    )

    band: Mapped[str] = mapped_column(
        tier_enum,
        nullable=False,
        server_default=sa.text("'unscoped'"),
    )

    verdict_label: Mapped[str | None] = mapped_column(
        sa.String(40),
        nullable=True,
    )

    cap_callout: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
    )

    confidence: Mapped[str | None] = mapped_column(
        sa.String(8),
        nullable=True,
    )

    score_breakdown: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    trust_labels: Mapped[list[Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        server_default=sa.text("'[]'::jsonb"),
    )

    pack_id: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
    )

    pack_version: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
    )

    pack_signature_verified: Mapped[bool | None] = mapped_column(
        sa.Boolean,
        nullable=True,
        server_default=sa.text("false"),
    )

    capabilities_present: Mapped[list[Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        server_default=sa.text("'[]'::jsonb"),
    )

    capabilities_absent: Mapped[list[Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        server_default=sa.text("'[]'::jsonb"),
    )

    family_tally: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        server_default=sa.text("'{}'::jsonb"),
    )

    visibility: Mapped[str] = mapped_column(
        visibility_enum,
        nullable=False,
        server_default=sa.text("'public'"),
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    rubric_version: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
    )

    engine_version: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
    )

    latency_ms: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    )

    scanned_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    idempotency_key: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        unique=True,
    )

    share_token: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        unique=True,
    )

    nonce: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
    )

    decoy: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
    )

    pack_sha256: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
    )

    pack_signature: Mapped[str | None] = mapped_column(
        sa.String(128),
        nullable=True,
    )

    pack_key_id: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
    )

    submit_token_sha256: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
    )

    vendor_reply: Mapped[str | None] = mapped_column(
        sa.String(1000),
        nullable=True,
    )

    vendor_reply_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    kind_tally: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    component_scan_run_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("scan_runs.id", ondelete="SET NULL"),
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
        return f"AgentRun(id={self.id!r})"
