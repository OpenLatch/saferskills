"""SQLAlchemy ORM for `access_log` (internal — no JSON-Schema source).

Write-only B2B-intel signal; the reader ships later. Rows carry a /24-(v4) or
/48-(v6) redacted IP, a closed-enum action, and the accessed item's content hash
(never a slug/URL). See .claude/rules/privacy.md + security.md § Vendor-data
isolation. Raw IPs are never exported; redaction happens at write time in the
middleware.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, text
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AccessLog(Base):
    __tablename__ = "access_log"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    item_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    http_referer_host: Mapped[str | None] = mapped_column(String(200), nullable=True)
