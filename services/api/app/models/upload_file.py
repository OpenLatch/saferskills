"""SQLAlchemy ORM for `upload_files` — transient per-run upload byte store.

The unlisted-upload counterpart to `artifact_blobs`: when a user uploads a
private (unlisted) artifact, its scanned text bytes are stored here per-run
(NO content-addressed dedup), so identical private bytes from two submitters
never share a row (avoids the dedup-induced privacy coupling — see
`.claude/rules/security.md` § Vendor-data isolation). Public uploads reuse the
deduped `artifact_blobs` store instead.

Like `artifact_blobs`, this is internal storage only — NOT part of the generated
entity pipeline (no `schemas/*.schema.json`, no Pydantic/Zod/TS DTO). Reached
only via `app/scan/persistence.py` (write) and `app/services/artifact_bytes.py`
(read). Rows are reaped with the run (FK CASCADE + `delete_run_cascade`) or on
90-day expiry; promote migrates the bytes into `artifact_blobs`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UploadFile(Base):
    __tablename__ = "upload_files"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    scan_run_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("scan_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    # null = binary/oversize sentinel (present-but-not-stored).
    content: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    is_binary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
