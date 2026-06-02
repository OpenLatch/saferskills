# DO NOT EDIT — regenerate via: pnpm run generate (scripts/generate_sqlalchemy_models.py)
"""VendorVerification SQLAlchemy model — maps to the `vendor_verifications` table."""

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.generated._base import Base, vendor_verification_state_enum


class VendorVerification(Base):
    """Vendor maintainer-verification token lifecycle (D-05 / D-06 / D-07 / D-08). A maintainer claims a catalog..."""

    __tablename__ = "vendor_verifications"

    __table_args__ = (
        sa.Index("idx_vendor_verifications_catalog_item_state", "catalog_item_id", "state"),
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

    token_hash_sha256: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
        unique=True,
    )

    issued_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    expires_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
    )

    redeemed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    verified_github_user: Mapped[str | None] = mapped_column(
        sa.String(100),
        nullable=True,
    )

    state: Mapped[str] = mapped_column(
        vendor_verification_state_enum,
        nullable=False,
        server_default=sa.text("'pending'"),
    )

    last_drift_check_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
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
        return f"VendorVerification(id={self.id!r}, catalog_item_id={self.catalog_item_id!r})"
