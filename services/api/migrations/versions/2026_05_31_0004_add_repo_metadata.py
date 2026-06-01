"""Add GitHub repo metadata to catalog_items.

Revision ID: 0004_add_repo_metadata
Revises: 0003_add_agent_compatibility
Create Date: 2026-05-31

Item-detail redesign — the page header + Package card surface GitHub stars,
forks, SPDX license, and the latest release tag. These are read-only mirrors of
public GitHub data, refreshed from api.github.com at scan time by
``app/services/repository_metadata.py``. All nullable (null until first fetch).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "0004_add_repo_metadata"
down_revision: str | None = "0003_add_agent_compatibility"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("catalog_items", sa.Column("github_stars", sa.Integer, nullable=True))
    op.add_column("catalog_items", sa.Column("github_forks", sa.Integer, nullable=True))
    op.add_column("catalog_items", sa.Column("license_spdx", sa.String(100), nullable=True))
    op.add_column("catalog_items", sa.Column("latest_version", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("catalog_items", "latest_version")
    op.drop_column("catalog_items", "license_spdx")
    op.drop_column("catalog_items", "github_forks")
    op.drop_column("catalog_items", "github_stars")
