"""Direct artifact upload + private (unlisted) scans (I-3.5).

Revision ID: 0008_add_upload_and_visibility
Revises: 0007_per_capability_scans
Create Date: 2026-06-01

Adds upload as a *second front-end* to the unchanged scan engine, plus the
visibility / capability-URL / lifecycle layer on top.

- `scan_runs` gains the run-level submission/idempotency/report/token columns:
  `visibility`, `source_kind`, `share_token` (UNIQUE), `expires_at`,
  `original_filename`, and `content_hash_sha256` (the durable artifactSha256
  source — the idempotency_key can't recover the raw artifact hash). `github_url`
  becomes nullable (uploads have no URL); `ref_sha` was already nullable.
- `scans.github_url` AND `scans.ref_sha` are relaxed to NULLABLE — upload
  fan-out creates per-capability `scans` rows with no GitHub URL/ref (no synthetic
  `upload://` sentinel). `scans.catalog_item_id` stays NOT NULL (every run gets a
  catalog_item — canonical for public, a per-run shadow row for unlisted).
- `catalog_items` gains denormalized `visibility`/`source_kind` + the shadow-row
  marker `owner_run_id` (FK scan_runs ON DELETE CASCADE); `github_org`/
  `github_repo`/`default_branch`/`github_url` relax to NULLABLE (uploads have no
  GitHub provenance).
- New `upload_files` — a transient per-run byte store (no dedup; mirrors
  `artifact_blobs` shape) for unlisted uploads.
- The `rate_limits.bucket` CHECK gains `private_lookup`.

The `scans -> scan_runs` FK stays `ON DELETE SET NULL` (migration 0007) — deletes
go through the explicit ordered `delete_run_cascade` routine, never the FK. Auto-
applies on boot under advisory lock `0x5AFE5C11` (`app/core/startup.py`).

`downgrade()` is best-effort on the NOT NULL re-assertions: a DB holding upload
rows (NULL `scans.github_url`/`ref_sha`, NULL `catalog_items.github_*`) cannot
re-assert NOT NULL, so those alters are guarded + logged like 0007's github_url.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# Revision identifiers, used by Alembic.
revision: str = "0008_add_upload_and_visibility"
down_revision: str | None = "0007_per_capability_scans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

VISIBILITY_VALUES = ("public", "unlisted")
SOURCE_KIND_VALUES = ("github", "upload")

# `rate_limits.bucket` CHECK lineage: 0001 -> 0006 (+artifact_download) -> here.
_OLD_BUCKETS = ("scan_submit", "scan_read", "item_read", "item_list", "artifact_download")
_NEW_BUCKETS = (*_OLD_BUCKETS, "private_lookup")


def _quoted(values: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _bucket_check(values: Sequence[str]) -> str:
    return f"bucket IN ({_quoted(values)})"


def upgrade() -> None:
    # ── scan_runs: run = submission / idempotency / report / token unit ────────
    op.add_column(
        "scan_runs",
        sa.Column("visibility", sa.String(20), nullable=False, server_default=sa.text("'public'")),
    )
    op.add_column(
        "scan_runs",
        sa.Column("source_kind", sa.String(20), nullable=False, server_default=sa.text("'github'")),
    )
    op.add_column("scan_runs", sa.Column("share_token", sa.String(64), nullable=True))
    op.add_column("scan_runs", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("scan_runs", sa.Column("original_filename", sa.String(255), nullable=True))
    # The DURABLE artifactSha256 source — idempotency_key cannot recover the hash.
    op.add_column("scan_runs", sa.Column("content_hash_sha256", sa.String(64), nullable=True))
    op.create_check_constraint(
        "chk_scan_runs_visibility", "scan_runs", f"visibility IN ({_quoted(VISIBILITY_VALUES)})"
    )
    op.create_check_constraint(
        "chk_scan_runs_source_kind", "scan_runs", f"source_kind IN ({_quoted(SOURCE_KIND_VALUES)})"
    )
    # A Postgres UNIQUE permits multiple NULLs, so public runs (share_token NULL)
    # never collide — only issued unlisted tokens are uniqueness-checked.
    op.create_unique_constraint("uq_scan_runs_share_token", "scan_runs", ["share_token"])
    # github_url was NOT NULL (0007); uploads have no URL. (ref_sha already NULL.)
    op.alter_column("scan_runs", "github_url", existing_type=sa.String(500), nullable=True)
    # Partial index for the expiry sweep (only unlisted rows ever expire).
    op.create_index(
        "idx_scan_runs_expires_at",
        "scan_runs",
        ["expires_at"],
        postgresql_where=sa.text("visibility = 'unlisted'"),
    )

    # ── scans: make per-capability rows insertable for uploads ────────────────
    # Uploads set both NULL — no synthetic "upload://" sentinel (sentinels leak
    # into the report UI as fake links). catalog_item_id stays NOT NULL.
    op.alter_column("scans", "github_url", existing_type=sa.String(500), nullable=True)
    op.alter_column("scans", "ref_sha", existing_type=sa.String(40), nullable=True)

    # ── catalog_items: denormalized visibility/source + shadow-row marker ──────
    op.add_column(
        "catalog_items",
        sa.Column("visibility", sa.String(20), nullable=False, server_default=sa.text("'public'")),
    )
    op.add_column(
        "catalog_items",
        sa.Column("source_kind", sa.String(20), nullable=False, server_default=sa.text("'github'")),
    )
    # owner_run_id ties a per-run SHADOW row to its run for CASCADE + sweep
    # (NULL on canonical public rows).
    op.add_column("catalog_items", sa.Column("owner_run_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_catalog_items_owner_run_id",
        "catalog_items",
        "scan_runs",
        ["owner_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "chk_catalog_items_visibility",
        "catalog_items",
        f"visibility IN ({_quoted(VISIBILITY_VALUES)})",
    )
    op.create_check_constraint(
        "chk_catalog_items_source_kind",
        "catalog_items",
        f"source_kind IN ({_quoted(SOURCE_KIND_VALUES)})",
    )
    op.create_index("idx_catalog_items_visibility", "catalog_items", ["visibility"])
    op.create_index(
        "idx_catalog_items_owner_run_id",
        "catalog_items",
        ["owner_run_id"],
        postgresql_where=sa.text("owner_run_id IS NOT NULL"),
    )
    # Uploads have no GitHub provenance — relax the NOT NULLs
    # (0007 already dropped UNIQUE(github_url); github_url is already nullable).
    op.alter_column("catalog_items", "github_org", existing_type=sa.String(100), nullable=True)
    op.alter_column("catalog_items", "github_repo", existing_type=sa.String(100), nullable=True)
    op.alter_column("catalog_items", "default_branch", existing_type=sa.String(200), nullable=True)

    # ── upload_files: transient per-run byte store (no dedup) ──────────────────
    op.create_table(
        "upload_files",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("scan_run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("path", sa.String(1024), nullable=False),
        sa.Column("content", sa.LargeBinary, nullable=True),  # null = binary/oversize sentinel
        sa.Column("byte_size", sa.Integer, nullable=False),
        sa.Column("is_binary", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_foreign_key(
        "fk_upload_files_scan_run_id",
        "upload_files",
        "scan_runs",
        ["scan_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("idx_upload_files_scan_run_id", "upload_files", ["scan_run_id"])

    # ── rate_limits: add the private_lookup bucket to the CHECK ────────────────
    op.drop_constraint("chk_rate_limits_bucket", "rate_limits", type_="check")
    op.create_check_constraint("chk_rate_limits_bucket", "rate_limits", _bucket_check(_NEW_BUCKETS))


def downgrade() -> None:
    # rate_limits CHECK back to the 0006 bucket set.
    op.drop_constraint("chk_rate_limits_bucket", "rate_limits", type_="check")
    op.create_check_constraint("chk_rate_limits_bucket", "rate_limits", _bucket_check(_OLD_BUCKETS))

    op.drop_index("idx_upload_files_scan_run_id", table_name="upload_files")
    op.drop_constraint("fk_upload_files_scan_run_id", "upload_files", type_="foreignkey")
    op.drop_table("upload_files")

    op.drop_index("idx_catalog_items_owner_run_id", table_name="catalog_items")
    op.drop_index("idx_catalog_items_visibility", table_name="catalog_items")
    op.drop_constraint("fk_catalog_items_owner_run_id", "catalog_items", type_="foreignkey")
    op.drop_constraint("chk_catalog_items_source_kind", "catalog_items", type_="check")
    op.drop_constraint("chk_catalog_items_visibility", "catalog_items", type_="check")
    op.drop_column("catalog_items", "owner_run_id")
    op.drop_column("catalog_items", "source_kind")
    op.drop_column("catalog_items", "visibility")
    # Best-effort NOT NULL re-assertion (fails if upload rows hold NULL github_*).
    for col in ("github_org", "github_repo", "default_branch"):
        try:
            op.alter_column("catalog_items", col, nullable=False)
        except Exception as exc:
            logger.warning("downgrade: leaving catalog_items.%s nullable (%s)", col, exc)

    try:
        op.alter_column("scans", "ref_sha", existing_type=sa.String(40), nullable=False)
        op.alter_column("scans", "github_url", existing_type=sa.String(500), nullable=False)
    except Exception as exc:
        logger.warning("downgrade: leaving scans.github_url/ref_sha nullable (%s)", exc)

    op.drop_index("idx_scan_runs_expires_at", table_name="scan_runs")
    try:
        op.alter_column("scan_runs", "github_url", existing_type=sa.String(500), nullable=False)
    except Exception as exc:
        logger.warning("downgrade: leaving scan_runs.github_url nullable (%s)", exc)
    op.drop_constraint("uq_scan_runs_share_token", "scan_runs", type_="unique")
    op.drop_constraint("chk_scan_runs_source_kind", "scan_runs", type_="check")
    op.drop_constraint("chk_scan_runs_visibility", "scan_runs", type_="check")
    op.drop_column("scan_runs", "content_hash_sha256")
    op.drop_column("scan_runs", "original_filename")
    op.drop_column("scan_runs", "expires_at")
    op.drop_column("scan_runs", "share_token")
    op.drop_column("scan_runs", "source_kind")
    op.drop_column("scan_runs", "visibility")
