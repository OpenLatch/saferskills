"""SQLAlchemy ORM for `repo_fetch_state` — per-repo conditional-fetch validators.

The durable bulk-scan path (`app/ingestion/tasks_scan.py`) resolves a repo's
HEAD ref through the unified App-token client and sends conditional headers
(`If-None-Match` / `If-Modified-Since`) so an unchanged repo costs a free 304
against the shared GitHub budget. The validators + the last-resolved ref SHA
live here, keyed by `github_url`.

`catalog_items` is per-capability (several rows per repo) and `scan_runs` is
per-run — neither is a stable per-repo home for these validators, so this is a
dedicated internal store. Like `artifact_blobs` / `upload_files` it is NOT part
of the generated entity pipeline (no `schemas/*.schema.json`, no Pydantic/Zod/TS
DTO, no wire exposure). Hand-written; registered in `app/models/__init__.py`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RepoFetchState(Base):
    __tablename__ = "repo_fetch_state"

    # The canonical GitHub repo URL is the natural per-repo key.
    github_url: Mapped[str] = mapped_column(String(1024), primary_key=True)
    # HTTP validators returned by api.github.com on the last successful resolve.
    etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # HEAD commit SHA of the default branch at the last successful resolve — the
    # content-change signal the scan job gates on (changed SHA → re-fetch + scan).
    resolved_ref_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # When this repo's ref was last resolved (200 or 304). A 304 / unchanged ref
    # bumps this without a scan (the cheap freshness-check path).
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
