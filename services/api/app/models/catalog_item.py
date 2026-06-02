"""SQLAlchemy ORM for `catalog_items`.

Hand-written full-column model. The generated stub at
`app/models/generated/catalog_item.py` is a W1 placeholder with only 4 columns;
Phase B (Track B) replaces it with this projection until the SQLAlchemy
generator gets full column emission.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.scan import Scan


class CatalogItem(Base):
    __tablename__ = "catalog_items"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    github_url: Mapped[str | None] = mapped_column(String(500), unique=True)
    # Nullable since I-3.5: uploaded artifacts have no GitHub provenance.
    github_org: Mapped[str | None] = mapped_column(String(100))
    github_repo: Mapped[str | None] = mapped_column(String(100))
    default_branch: Mapped[str | None] = mapped_column(String(200))
    popularity_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    popularity_score: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    agent_compatibility: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    github_stars: Mapped[int | None] = mapped_column(Integer)
    github_forks: Mapped[int | None] = mapped_column(Integer)
    license_spdx: Mapped[str | None] = mapped_column(String(100))
    latest_version: Mapped[str | None] = mapped_column(String(100))
    content_hash_sha256: Mapped[str | None] = mapped_column(String(64))
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    sources: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    item_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    # ── Upload / visibility (I-3.5) ───────────────────────────────────────────
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, server_default="'public'")
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default="'github'")
    # Shadow-row marker: NULL on canonical public rows, set on per-run unlisted
    # shadow rows (FK scan_runs ON DELETE CASCADE — see D-UP-27).
    owner_run_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("scan_runs.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    scans: Mapped[list[Scan]] = relationship(
        back_populates="catalog_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
