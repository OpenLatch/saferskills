# DO NOT EDIT — regenerate via: pnpm run generate (scripts/generate_sqlalchemy_models.py)
"""IngestionEvent SQLAlchemy model — maps to the `ingestion_events` table."""

from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.generated._base import Base


class IngestionEvent(Base):
    """One row per adapter fetch (outbox pattern, D-04-08). Immutable, append-only, replayable: re-deriving the..."""

    __tablename__ = "ingestion_events"

    __table_args__ = (
        sa.Index("idx_ingestion_events_source", "source"),
        sa.Index(
            "idx_ingestion_events_unapplied",
            "applied_at",
            postgresql_where=sa.text("applied_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    )

    source: Mapped[str] = mapped_column(
        sa.String(50),
        nullable=False,
    )

    source_id: Mapped[str] = mapped_column(
        sa.String(500),
        nullable=False,
    )

    http_status: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
    )

    body_sha256: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
    )

    etag: Mapped[str | None] = mapped_column(
        sa.String(200),
        nullable=True,
    )

    fetched_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    duration_ms: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    )

    from_cache: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("false"),
    )

    fetch_tier: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("1"),
    )

    payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    applied_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    error_reason: Mapped[str | None] = mapped_column(
        sa.String(50),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"IngestionEvent(id={self.id!r})"
