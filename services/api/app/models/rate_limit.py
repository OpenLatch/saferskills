"""SQLAlchemy ORM for `rate_limits` (composite PK)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RateLimit(Base):
    __tablename__ = "rate_limits"

    ip_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    bucket: Mapped[str] = mapped_column(String(20), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
