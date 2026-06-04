"""SQLAlchemy ORM for `install_events` (internal — no JSON-Schema source).

One row per opt-in install reported by the install CLI (D-05-31). Backs the real
`install_activity` GROUP-BY aggregate on the item-detail surface (this_week /
this_month / all_time + agent distribution), replacing the deterministic mock.

Internal storage only — NOT part of the generated entity pipeline (no
`schemas/*.schema.json`, no Pydantic/Zod/TS DTO of the model itself, never
serialized through a response_model). Hand-written, registered in
`app/models/__init__.py`; mirrors `access_log` / `upload_file`.

Retention differs from `access_log`: rows are RETAINED (redacted IP, closed-enum,
no PII) so the `all_time` count survives — see `.claude/rules/privacy.md` +
`security.md` § Vendor-data isolation. `redacted_ip` is masked to /24 (v4) or /48
(v6) at write time in the router; a raw IP is never stored.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

# Reuse the existing native `kind` PG enum object (migration 0009) so the same
# type is registered once on Base.metadata.
from app.models.base import Base
from app.models.generated._base import kind_enum

# Native PG enum `agent` — the 8 canonical agent ids (created in migration 0015).
# Mirrors app/services/agent_compat.py::AgentName / ALL_AGENTS.
AGENT_VALUES: tuple[str, ...] = (
    "claude-code",
    "cursor",
    "codex",
    "copilot",
    "windsurf",
    "cline",
    "gemini",
    "openclaw",
)
agent_enum = sa.Enum(
    *AGENT_VALUES,
    name="agent",
    native_enum=True,
    create_type=False,
    create_constraint=False,
)


class InstallEvent(Base):
    __tablename__ = "install_events"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    catalog_item_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("catalog_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent: Mapped[str] = mapped_column(agent_enum, nullable=False)
    kind: Mapped[str] = mapped_column(kind_enum, nullable=False)
    cli_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # /24-(v4) or /48-(v6) redacted prefix — never a raw IP (privacy.md).
    redacted_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
