"""SQLAlchemy ORM for `admin_audit_log` (internal — no JSON-Schema source).

Every admin endpoint mutation emits one row (security.md audit invariant). The
table ships ahead of the admin endpoints + CLI so the audit surface exists from
day one.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_admin_key_fp: Mapped[str] = mapped_column(String(20), nullable=False)
    target: Mapped[str | None] = mapped_column(String(500), nullable=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
