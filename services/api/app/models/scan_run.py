"""SQLAlchemy ORM for `scan_runs` — the repo-level grouping over per-capability scans.

A repo submit creates one `scan_runs` row. The engine discovers N capabilities,
ensures N catalog items, and fans out to N `scans` rows (each linked via
`scans.scan_run_id`). The repo aggregate (mean of the per-capability scores) and
the by-kind tally live here; `/scans/runs/<run_id>` is the repo report surface.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.scan import Scan
    from app.models.upload_file import UploadFile


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # Nullable since I-3.5: uploads have no GitHub URL.
    github_url: Mapped[str | None] = mapped_column(String(500))
    ref_sha: Mapped[str | None] = mapped_column(String(40))
    repo_aggregate_score: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    repo_tier: Mapped[str] = mapped_column(String(20), nullable=False, server_default="'unscoped'")
    kind_tally: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    capability_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rubric_version: Mapped[str] = mapped_column(String(40), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="'pending'")
    # ── Upload / visibility (I-3.5) ───────────────────────────────────────────
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, server_default="'public'")
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default="'github'")
    share_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    # Durable artifactSha256 source (sha256 of the sorted {path: sha256} map).
    content_hash_sha256: Mapped[str | None] = mapped_column(String(64))
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    scans: Mapped[list[Scan]] = relationship(back_populates="scan_run")
    upload_files: Mapped[list[UploadFile]] = relationship(
        back_populates="scan_run", cascade="all, delete-orphan", passive_deletes=True
    )
