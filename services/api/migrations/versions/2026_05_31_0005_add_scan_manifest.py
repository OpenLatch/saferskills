"""Add manifest_path + manifest_source to scans.

Revision ID: 0005_add_scan_manifest
Revises: 0004_add_repo_metadata
Create Date: 2026-05-31

Item-detail Source tab — capture the primary public manifest (SKILL.md / README)
at scan time, size-capped, and surface it on the item page. This is public repo
content displayed verbatim — distinct from the scan trace (which never stores
raw artifact payload). Both columns nullable (null until a scan captures one).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "0005_add_scan_manifest"
down_revision: str | None = "0004_add_repo_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scans", sa.Column("manifest_path", sa.String(255), nullable=True))
    op.add_column("scans", sa.Column("manifest_source", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("scans", "manifest_source")
    op.drop_column("scans", "manifest_path")
