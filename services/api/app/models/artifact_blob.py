"""SQLAlchemy ORM for `artifact_blobs` — content-addressed scanned-file storage.

Internal storage table for the stored-public-artifact-snapshot feature (Phase B).
Each row is one unique file body keyed by its SHA-256, so identical files across
scans/items dedup to a single blob. The `scans.file_hashes` JSONB maps
`{path -> sha256 | null}` per scan (null = known-but-not-stored binary), joining
the snapshot back to its files.

This is a content-storage subsystem, NOT part of the generated entity pipeline:
there is no `schemas/*.schema.json`, no Pydantic/Zod/TS DTO. The bytes are
verbatim public-repo content at the scanned ref (per `.claude/rules/security.md`
§ Vendor-data isolation → stored public artifact snapshots). The scan *trace*
remains no-raw-payload — this is a separate, explicitly public feature.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, LargeBinary, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ArtifactBlob(Base):
    __tablename__ = "artifact_blobs"

    # Content-addressed primary key: the lowercase hex SHA-256 of `content`.
    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    is_binary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
