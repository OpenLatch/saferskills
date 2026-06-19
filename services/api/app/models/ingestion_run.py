"""SQLAlchemy ORM for `ingestion_runs` (internal — no JSON-Schema source).

One row per ingestion cycle attempt. Written by `app/ingestion/tasks.py` at the
cycle chokepoint in INDEPENDENT sessions (2 commits: a `running` row when the
cycle starts, then a `succeeded`/`failed` update when it ends) — so a cycle whose
own transaction rolls back still leaves a durable failure record. Backs the
eagle-eye health view (`GET /api/v1/admin/sources` + `…/{source}/runs`) and the
`saferskills-admin sources dashboard` TUI.

Like `crawler_cursors` / `upload_file`, this is internal storage only — NOT part
of the generated entity pipeline (no `schemas/*.schema.json`, no Pydantic/Zod/TS
DTO, never serialized through a response_model). Hand-written, registered in
`app/models/__init__.py`. Swept after 90 days (`app/core/sweeps.py`).

`error_message` stores at most 2048 chars of the exception text — never raw
artifact payload (the scan-trace no-raw-payload invariant, `security.md`).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    # scheduled (periodic) | force (admin force-cycle) | manual (run_one_cycle)
    # | reconcile (ingestion_overdue_reconciler re-firing a missed cron tick)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    # running | succeeded | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    items_seen: Mapped[int | None] = mapped_column(Integer, nullable=True)
    items_added: Mapped[int | None] = mapped_column(Integer, nullable=True)
    items_updated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    http_304_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    http_5xx_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    error_class: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
