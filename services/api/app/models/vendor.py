"""SQLAlchemy ORM for `vendor_verifications` + `vendor_responses`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class VendorVerification(Base):
    __tablename__ = "vendor_verifications"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    catalog_item_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("catalog_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_github_user: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(20), nullable=False, server_default="'pending'")
    last_drift_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    responses: Mapped[list[VendorResponse]] = relationship(
        back_populates="verification",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class VendorResponse(Base):
    __tablename__ = "vendor_responses"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    catalog_item_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("catalog_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    vendor_verification_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("vendor_verifications.id", ondelete="CASCADE"),
        nullable=False,
    )
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    verification: Mapped[VendorVerification] = relationship(back_populates="responses")
