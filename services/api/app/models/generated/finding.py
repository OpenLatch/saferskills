# DO NOT EDIT — regenerate via: pnpm run generate (scripts/generate_sqlalchemy_models.py)
"""Finding SQLAlchemy model — maps to the `findings` table."""

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.generated._base import Base, severity_enum, status_at_scan_enum, sub_score_enum


class Finding(Base):
    """A single rule fire on a scanned artifact. Hashed-only evidence (matchedContentSha256) — never raw scanned..."""

    __tablename__ = "findings"

    __table_args__ = (
        sa.Index("idx_findings_scan_id", "scan_id"),
        sa.Index("idx_findings_rule_id", "rule_id"),
        sa.Index("idx_findings_sub_score_severity", "sub_score", "severity"),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    )

    scan_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )

    rule_id: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
    )

    severity: Mapped[str] = mapped_column(
        severity_enum,
        nullable=False,
    )

    sub_score: Mapped[str] = mapped_column(
        sub_score_enum,
        nullable=False,
    )

    penalty: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    )

    status_at_scan: Mapped[str] = mapped_column(
        status_at_scan_enum,
        nullable=False,
    )

    file_path: Mapped[str] = mapped_column(
        sa.String(1024),
        nullable=False,
    )

    line_start: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
    )

    line_end: Mapped[int | None] = mapped_column(
        sa.Integer,
        nullable=True,
    )

    matched_content_sha256: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
    )

    remediation_link: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
    )

    rubric_version: Mapped[str] = mapped_column(
        sa.Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    def __repr__(self) -> str:
        return f"Finding(id={self.id!r}, rule_id={self.rule_id!r})"
