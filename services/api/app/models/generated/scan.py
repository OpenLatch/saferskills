# DO NOT EDIT — regenerate via: pnpm run generate (scripts/generate_sqlalchemy_models.py)
"""Scan SQLAlchemy model — maps to the `scans` table."""

from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.generated._base import Base, scan_source_enum, tier_enum


class Scan(Base):
    """Public scan report for a CatalogItem. PRD-locked 5-axis sub-score taxonomy and 5-tier severity ladder per..."""

    __tablename__ = "scans"

    __table_args__ = (
        sa.Index("idx_scans_catalog_item_id_scanned_at", "catalog_item_id", "scanned_at"),
        sa.Index("idx_scans_tier", "tier"),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    )

    catalog_item_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("catalog_items.id", ondelete="CASCADE"),
        nullable=False,
    )

    idempotency_key: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        unique=True,
    )

    github_url: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
    )

    ref_sha: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
    )

    aggregate_score: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
    )

    tier: Mapped[str] = mapped_column(
        tier_enum,
        nullable=False,
    )

    sub_scores: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    score_breakdown: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    trace_truncated: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("false"),
    )

    omitted_findings_count: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    )

    file_hashes: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
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

    scanned_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    latency_ms: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
    )

    source: Mapped[str] = mapped_column(
        scan_source_enum,
        nullable=False,
    )

    install_spec: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    scan_run_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("scan_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    component_path: Mapped[str | None] = mapped_column(
        sa.String(1024),
        nullable=True,
    )

    manifest_path: Mapped[str | None] = mapped_column(
        sa.String(255),
        nullable=True,
    )

    manifest_source: Mapped[str | None] = mapped_column(
        sa.Text,
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
        return f"Scan(id={self.id!r}, catalog_item_id={self.catalog_item_id!r})"
