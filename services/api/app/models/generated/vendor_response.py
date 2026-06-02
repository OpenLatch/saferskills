# DO NOT EDIT — regenerate via: pnpm run generate (scripts/generate_sqlalchemy_models.py)
"""VendorResponse SQLAlchemy model — maps to the `vendor_responses` table."""

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.generated._base import Base


class VendorResponse(Base):
    """Verified-vendor public response on a catalog item (PRD §11.2). Transparency over erasure — old versions..."""

    __tablename__ = "vendor_responses"

    __table_args__ = (
        sa.Index("idx_vendor_responses_catalog_item_version_desc", "catalog_item_id", "version"),
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

    vendor_verification_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("vendor_verifications.id", ondelete="CASCADE"),
        nullable=False,
    )

    body_markdown: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
    )

    submitted_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    version: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("1"),
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    def __repr__(self) -> str:
        return f"VendorResponse(id={self.id!r}, catalog_item_id={self.catalog_item_id!r})"
