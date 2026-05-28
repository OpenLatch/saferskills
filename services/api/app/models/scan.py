"""SQLAlchemy ORM for `scans`, `findings`, `scan_events`."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.catalog_item import CatalogItem


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
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    github_url: Mapped[str] = mapped_column(String(500), nullable=False)
    ref_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    aggregate_score: Mapped[int] = mapped_column(Integer, nullable=False)
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    sub_scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    file_hashes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
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
    scan_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    completion_pct: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    emitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    scan: Mapped[Scan] = relationship(back_populates="events")
