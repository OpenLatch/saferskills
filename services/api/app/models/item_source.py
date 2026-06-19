"""SQLAlchemy ORM for `item_sources`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ItemSource(Base):
    __tablename__ = "item_sources"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    catalog_item_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("catalog_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    registry_id: Mapped[str] = mapped_column(String(40), nullable=False)
    registry_url: Mapped[str] = mapped_column(String(500), nullable=False)
    # Per-listing health (migration 0011): active|paused|blocked|disabled.
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))
    listed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
