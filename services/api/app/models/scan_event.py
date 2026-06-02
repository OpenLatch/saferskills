"""SQLAlchemy ORM for `scan_events` — per-stage SSE-catch-up progress events.

Hand-written internal model — `scan_events` has no JSON-Schema source-of-truth
(it is an SSE replay buffer, never a wire DTO), so it stays out of the generated
codegen pipeline alongside item_source / rate_limit / upload_file / artifact_blob.

Created by migration `0002_add_scan_events`. The in-process worker appends a row
at each stage boundary; SSE consumers replay from `event_seq > last_event_id`
then LISTEN for live `NOTIFY` payloads on channel `scan_progress_<run_id>`. The
`scan` / `scan_run` relationships are attached centrally in
`app/models/_relationships.py`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ScanEvent(Base):
    __tablename__ = "scan_events"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Repo-scan grouping — progress events re-key onto the run (channel
    # `scan_progress_<run_id>`; see `app/queue/scan_runner.py`). Run-level events
    # carry `scan_run_id` and leave `scan_id` null.
    scan_run_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("scan_runs.id", ondelete="CASCADE"),
        nullable=True,
    )
    # Legacy per-capability link — nullable since the SSE re-key (migration 0007)
    # keys progress on the run, not an individual capability scan.
    scan_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=True,
    )
    event_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    completion_pct: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    emitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
