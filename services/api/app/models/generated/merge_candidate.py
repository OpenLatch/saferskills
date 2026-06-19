# DO NOT EDIT — regenerate via: pnpm run generate (scripts/generate_sqlalchemy_models.py)
"""MergeCandidate SQLAlchemy model — maps to the `merge_candidates` table."""

from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.generated._base import Base


class MergeCandidate(Base):
    """Pending merge of two items that share a fuzzy name similarity but no canonical-ID match. Wikidata..."""

    __tablename__ = "merge_candidates"

    __table_args__ = (
        sa.Index("uq_merge_candidates_pair", "left_artifact_id", "right_artifact_id", unique=True),
        sa.Index(
            "idx_merge_candidates_pending", "status", postgresql_where=sa.text("status = 'pending'")
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    )

    left_artifact_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("catalog_items.id", ondelete="CASCADE"),
        nullable=False,
    )

    right_artifact_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("catalog_items.id", ondelete="CASCADE"),
        nullable=False,
    )

    rapidfuzz_score: Mapped[float] = mapped_column(
        sa.Float(precision=24),
        nullable=False,
    )

    jaro_winkler_score: Mapped[float] = mapped_column(
        sa.Float(precision=24),
        nullable=False,
    )

    signals: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )

    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        server_default=sa.text("'pending'"),
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    decided_by: Mapped[str | None] = mapped_column(
        sa.String(20),
        nullable=True,
    )

    decided_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    decision_note: Mapped[str | None] = mapped_column(
        sa.String(500),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"MergeCandidate(id={self.id!r})"
