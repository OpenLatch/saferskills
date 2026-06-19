"""SQLAlchemy ORM for `crawler_cursors` (internal — no JSON-Schema source).

One row per adapter source. Holds the resume cursor + per-source health/status
(active|paused|blocked|disabled) used by the framework + the /sources
dashboard. Seeded with 14 rows by migration 0011.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CrawlerCursor(Base):
    __tablename__ = "crawler_cursors"

    source: Mapped[str] = mapped_column(String(50), primary_key=True)
    cursor_value: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_successful_cycle_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_attempted_cycle_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consecutive_failure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))
    status_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
