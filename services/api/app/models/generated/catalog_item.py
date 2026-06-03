# DO NOT EDIT — regenerate via: pnpm run generate (scripts/generate_sqlalchemy_models.py)
"""CatalogItem SQLAlchemy model — maps to the `catalog_items` table."""

from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.generated._base import (
    Base,
    availability_enum,
    kind_enum,
    popularity_rank_tier_enum,
    popularity_tier_enum,
    quality_tier_enum,
    source_kind_enum,
    visibility_enum,
)


class CatalogItem(Base):
    """A single capability in the SaferSkills catalog (a skill, MCP server, hook, plugin, or rules artifact)...."""

    __tablename__ = "catalog_items"

    __table_args__ = (
        sa.Index("idx_catalog_items_kind", "kind"),
        sa.Index("idx_catalog_items_popularity_tier", "popularity_tier"),
        sa.Index(
            "idx_catalog_items_active",
            "popularity_tier",
            "updated_at",
            postgresql_where=sa.text("archived = false"),
        ),
        sa.Index("idx_catalog_items_github_url", "github_url"),
        sa.Index("idx_catalog_items_visibility", "visibility"),
        sa.Index(
            "idx_catalog_items_owner_run_id",
            "owner_run_id",
            postgresql_where=sa.text("owner_run_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    )

    kind: Mapped[str] = mapped_column(
        kind_enum,
        nullable=False,
    )

    slug: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
        unique=True,
    )

    display_name: Mapped[str] = mapped_column(
        sa.String(200),
        nullable=False,
    )

    github_url: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
    )

    github_org: Mapped[str | None] = mapped_column(
        sa.String(100),
        nullable=True,
    )

    github_repo: Mapped[str | None] = mapped_column(
        sa.String(100),
        nullable=True,
    )

    default_branch: Mapped[str | None] = mapped_column(
        sa.String(200),
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

    popularity_tier: Mapped[str] = mapped_column(
        popularity_tier_enum,
        nullable=False,
    )

    popularity_score: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    )

    agent_compatibility: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
    )

    github_stars: Mapped[int | None] = mapped_column(
        sa.Integer,
        nullable=True,
    )

    github_forks: Mapped[int | None] = mapped_column(
        sa.Integer,
        nullable=True,
    )

    license_spdx: Mapped[str | None] = mapped_column(
        sa.String(100),
        nullable=True,
    )

    latest_version: Mapped[str | None] = mapped_column(
        sa.String(100),
        nullable=True,
    )

    content_hash_sha256: Mapped[str | None] = mapped_column(
        sa.Text,
        nullable=True,
    )

    archived: Mapped[bool] = mapped_column(
        sa.Boolean,
        nullable=False,
        server_default=sa.text("false"),
    )

    sources: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
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

    item_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )

    availability: Mapped[str] = mapped_column(
        availability_enum,
        nullable=False,
        server_default=sa.text("'available'"),
    )

    quality_tier: Mapped[str] = mapped_column(
        quality_tier_enum,
        nullable=False,
        server_default=sa.text("'medium'"),
    )

    quality_signals: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )

    fork_of_repo_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("catalog_items.id", ondelete="SET NULL"),
        nullable=True,
    )

    popularity_breakdown: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )

    kind_signals: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    )

    consecutive404_count: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    )

    last_seen200_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    pushed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    popularity_rank_tier: Mapped[str] = mapped_column(
        popularity_rank_tier_enum,
        nullable=False,
        server_default=sa.text("'long_tail'"),
    )

    last_deep_scan_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    last_lite_scan_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    owner_run_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("scan_runs.id", ondelete="CASCADE"),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"CatalogItem(id={self.id!r}, slug={self.slug!r})"
