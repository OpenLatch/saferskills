# DO NOT EDIT — regenerate via: pnpm run generate (scripts/generate_sqlalchemy_models.py)
"""ScanRun SQLAlchemy model — maps to the `scan_runs` table."""

from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.generated._base import (
    Base,
    scan_run_status_enum,
    scan_source_enum,
    source_kind_enum,
    tier_enum,
    visibility_enum,
)


class ScanRun(Base):
    """Full report for one repo scan (a `scan_runs` row): the consolidated repo score, the by-kind tally, and..."""

    __tablename__ = "scan_runs"

    __table_args__ = (
        sa.Index(
            "idx_scan_runs_expires_at",
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

    github_url: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
    )

    repo_aggregate_score: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    )

    repo_tier: Mapped[str] = mapped_column(
        tier_enum,
        nullable=False,
        server_default=sa.text("'unscoped'"),
    )

    kind_tally: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )

    capability_count: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    )

    scanned_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
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

    source: Mapped[str] = mapped_column(
        scan_source_enum,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        scan_run_status_enum,
        nullable=False,
        server_default=sa.text("'pending'"),
    )

    ref_sha: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
    )

    visibility: Mapped[str] = mapped_column(
        visibility_enum,
        nullable=False,
        server_default=sa.text("'public'"),
    )

    source_kind: Mapped[str] = mapped_column(
        source_kind_enum,
        nullable=False,
        server_default=sa.text("'github'"),
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    idempotency_key: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        unique=True,
    )

    file_count: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    )

    content_hash_sha256: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
    )

    original_filename: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
    )

    share_token: Mapped[str | None] = mapped_column(
        sa.String(64),
        nullable=True,
        unique=True,
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
        return f"ScanRun(id={self.id!r})"
