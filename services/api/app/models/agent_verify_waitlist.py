"""SQLAlchemy ORM for `agent_verify_waitlist` (internal — no JSON-Schema source).

One row per "Request independent verification" demand signal recorded by the Agent
Report waitlist tile (I-5.6, D-5.6-08). Records that someone wants the (out-of-scope)
independently-observed verify tier — an account-free, email-OPTIONAL demand capture.

Internal storage only — NOT part of the generated entity pipeline (no
`schemas/*.schema.json`, no Pydantic/Zod/TS DTO of the model itself, never
serialized through a response_model). Hand-written, registered in
`app/models/__init__.py`; mirrors `install_event` / `access_log`.

`redacted_ip` is masked to /24 (v4) or /48 (v6) at write time in the router; a raw
IP is never stored (`.claude/rules/privacy.md`). `email` is optional + only stored
when the requester chooses to leave one. Rows are RETAINED (no PII beyond the
opt-in email) — the demand signal is the point.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AgentVerifyWaitlist(Base):
    __tablename__ = "agent_verify_waitlist"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Optional contact — only present when the requester left one (the tile is
    # account-free + email-optional). Never required, never a unique key.
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # /24-(v4) or /48-(v6) redacted prefix — never a raw IP (privacy.md).
    redacted_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
