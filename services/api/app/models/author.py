"""SQLAlchemy ORM for `authors` (internal — no JSON-Schema source).

One row per GitHub author/org seen during ingestion. `github_id` is nullable;
a nightly Phase C backfill task resolves it via api.github.com/users/{login}.
The partial unique index `uq_authors_github_id_when_known` (migration 0010)
excludes NULLs so multiple unknown-author rows coexist.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Author(Base):
    __tablename__ = "authors"

    github_username: Mapped[str] = mapped_column(String(100), primary_key=True)
    github_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
