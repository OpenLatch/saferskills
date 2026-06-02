"""SQLAlchemy ORM for `scans`, `findings`, `scan_events`."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.catalog_item import CatalogItem
    from app.models.scan_run import ScanRun


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    catalog_item_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("catalog_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The repo scan this per-capability scan belongs to. Nullable (SET NULL on
    # run delete); backfilled 1:1 for legacy/seed scans by migration 0007.
    scan_run_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("scan_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Relative path of the capability subtree within the repo ("" / null for a
    # whole-repo capability). Surfaces the scanned component on the report.
    component_path: Mapped[str | None] = mapped_column(String(1024))
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # Nullable since I-3.5: upload fan-out creates scans with no GitHub URL/ref
    # (no synthetic "upload://" sentinel — sentinels leak into the UI as links).
    github_url: Mapped[str | None] = mapped_column(String(500))
    ref_sha: Mapped[str | None] = mapped_column(String(40))
    aggregate_score: Mapped[int] = mapped_column(Integer, nullable=False)
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    sub_scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    file_hashes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Primary public manifest (SKILL.md / README) captured at scan time, size-capped.
    # Public repo content surfaced on the item Source tab — not a scan-trace payload.
    manifest_path: Mapped[str | None] = mapped_column(String(255))
    manifest_source: Mapped[str | None] = mapped_column(Text)
    trace_truncated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    omitted_findings_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rubric_version: Mapped[str] = mapped_column(String(40), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(40), nullable=False)
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    catalog_item: Mapped[CatalogItem] = relationship(back_populates="scans")
    scan_run: Mapped[ScanRun | None] = relationship(back_populates="scans")
    findings: Mapped[list[Finding]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    events: Mapped[list[ScanEvent]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    scan_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    sub_score: Mapped[str] = mapped_column(String(20), nullable=False)
    penalty: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status_at_scan: Mapped[str] = mapped_column(String(20), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    line_start: Mapped[int] = mapped_column(Integer, nullable=False)
    line_end: Mapped[int | None] = mapped_column(Integer)
    matched_content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    remediation_link: Mapped[str] = mapped_column(String(500), nullable=False)
    rubric_version: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    scan: Mapped[Scan] = relationship(back_populates="findings")


class ScanEvent(Base):
    """Per-stage progress event for SSE catch-up replay. Created by Phase B
    migration `0002_add_scan_events`. The in-process worker appends a row at
    each stage boundary; SSE consumers replay from `event_seq > last_event_id`
    then LISTEN for live `NOTIFY` payloads on channel `scan_progress_<id>`.
    """

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

    scan: Mapped[Scan | None] = relationship(back_populates="events")
    scan_run: Mapped[ScanRun | None] = relationship()
