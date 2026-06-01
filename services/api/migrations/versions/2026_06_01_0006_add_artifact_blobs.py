"""Add artifact_blobs — content-addressed scanned-file storage.

Revision ID: 0006_add_artifact_blobs
Revises: 0005_add_scan_manifest
Create Date: 2026-06-01

Stored public artifact snapshots (Phase B/C): persist the raw bytes of every
scanned text file, deduped by SHA-256, so the item page can render real
line-level version diffs and serve a SaferSkills-built `.zip`.

- `artifact_blobs(sha256 PK -> content bytea)` is the new dedup store.
- `scans.file_hashes` (JSONB) and `catalog_items.content_hash_sha256` already
  exist from migration 0001 — no DDL here; they are finally *populated* by the
  snapshot-capture path in `app/scan/persistence.py`.

Verbatim public-repo bytes at the scanned ref — reproduction of already-public
data, not new disclosure (see `.claude/rules/security.md` § Vendor-data
isolation). Deletion remedy is the vendor-appeals path. Auto-applies on boot via
`app/core/startup.py` under the `pg_advisory_lock`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "0006_add_artifact_blobs"
down_revision: str | None = "0005_add_scan_manifest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# `rate_limits.bucket` CHECK (from migration 0001) — the served-zip download
# endpoint adds a new bucket, so the constraint is recreated to include it.
_OLD_BUCKETS = ("scan_submit", "scan_read", "item_read", "item_list")
_NEW_BUCKETS = (*_OLD_BUCKETS, "artifact_download")


def _bucket_check(values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"bucket IN ({quoted})"


def upgrade() -> None:
    op.create_table(
        "artifact_blobs",
        sa.Column("sha256", sa.String(64), primary_key=True),
        sa.Column("content", sa.LargeBinary, nullable=False),
        sa.Column("byte_size", sa.Integer, nullable=False),
        sa.Column("is_binary", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Allow the new `artifact_download` rate-limit bucket.
    op.drop_constraint("chk_rate_limits_bucket", "rate_limits", type_="check")
    op.create_check_constraint("chk_rate_limits_bucket", "rate_limits", _bucket_check(_NEW_BUCKETS))


def downgrade() -> None:
    op.drop_constraint("chk_rate_limits_bucket", "rate_limits", type_="check")
    op.create_check_constraint("chk_rate_limits_bucket", "rate_limits", _bucket_check(_OLD_BUCKETS))
    op.drop_table("artifact_blobs")
