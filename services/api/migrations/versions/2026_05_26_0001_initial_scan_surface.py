"""initial scan surface — 7 product tables.

Revision ID: 0001_initial_scan_surface
Revises:
Create Date: 2026-05-26

Hand-written migration for Phase A (W2 Initiative I-02). Adds the 7 product
tables that back the scan-engine + vendor-appeals surfaces. The 8th queue
table (`scan_jobs`) is provisioned by `procrastinate.schema.apply()` in
Phase B when the worker process group lands.

All primary keys are UUIDv7 (PostgreSQL 17 `gen_uuid_v7()`, locked decision D-28).
All `created_at` / `updated_at` default to `now()`; `updated_at` is bumped at
the application layer (SQLAlchemy event listener) when Phase B adds writes.

See `.local/.brainstorms/backend-core/plan/01-data-rubric-seed-rules.md`
§ Alembic migration for the field-by-field rationale.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# Revision identifiers, used by Alembic.
revision: str = "0001_initial_scan_surface"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


KIND_VALUES = ("skill", "mcp_server", "hook", "plugin", "rules")
POPULARITY_TIER_VALUES = ("indexed", "lite", "deep", "on_demand")
TIER_VALUES = ("green", "yellow", "orange", "red", "unscoped")
SCAN_SOURCE_VALUES = ("submission", "ingestion", "rescan_drift", "rescan_appeal")
SEVERITY_VALUES = ("info", "low", "medium", "high", "critical")
SUB_SCORE_VALUES = ("security", "supply_chain", "maintenance", "transparency", "community")
STATUS_AT_SCAN_VALUES = ("shadow", "active")
VENDOR_VERIFICATION_STATE_VALUES = ("pending", "verified", "expired", "revoked")
REGISTRY_ID_VALUES = (
    "github_topic",
    "mcp_registry",
    "npm",
    "pypi",
    "clawhub",
    "skillsmp",
    "mcp_so",
    "smithery",
    "glama",
    "pulsemcp",
    "anthropics_skills",
    "user_submission",
    "vendor_verified",
)
RATE_LIMIT_BUCKET_VALUES = ("scan_submit", "scan_read", "item_read", "item_list")


def _check_in(column: str, values: Sequence[str], name: str) -> sa.CheckConstraint:
    quoted = ", ".join(f"'{v}'" for v in values)
    return sa.CheckConstraint(f"{column} IN ({quoted})", name=name)


def upgrade() -> None:
    # ── catalog_items ─────────────────────────────────────────────────────
    op.create_table(
        "catalog_items",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_uuid_v7()")
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("github_url", sa.String(500), nullable=True),
        sa.Column("github_org", sa.String(100), nullable=False),
        sa.Column("github_repo", sa.String(100), nullable=False),
        sa.Column("default_branch", sa.String(200), nullable=False),
        sa.Column("popularity_tier", sa.String(20), nullable=False),
        sa.Column("popularity_score", sa.Integer, nullable=False, server_default="0"),
        sa.Column("content_hash_sha256", sa.String(64), nullable=True),
        sa.Column("archived", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("sources", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("slug", name="uq_catalog_items_slug"),
        sa.UniqueConstraint("github_url", name="uq_catalog_items_github_url"),
        _check_in("kind", KIND_VALUES, "chk_catalog_items_kind"),
        _check_in("popularity_tier", POPULARITY_TIER_VALUES, "chk_catalog_items_popularity_tier"),
    )
    op.create_index("idx_catalog_items_kind", "catalog_items", ["kind"])
    op.create_index("idx_catalog_items_popularity_tier", "catalog_items", ["popularity_tier"])
    op.create_index(
        "idx_catalog_items_active",
        "catalog_items",
        ["popularity_tier", "updated_at"],
        postgresql_where=sa.text("archived = false"),
    )

    # ── scans ─────────────────────────────────────────────────────────────
    op.create_table(
        "scans",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_uuid_v7()")
        ),
        sa.Column(
            "catalog_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("catalog_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("github_url", sa.String(500), nullable=False),
        sa.Column("ref_sha", sa.String(40), nullable=False),
        sa.Column("aggregate_score", sa.Integer, nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("sub_scores", JSONB, nullable=False),
        sa.Column("score_breakdown", JSONB, nullable=False),
        sa.Column("file_hashes", JSONB, nullable=True),
        sa.Column("trace_truncated", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("omitted_findings_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rubric_version", sa.String(40), nullable=False),
        sa.Column("engine_version", sa.String(40), nullable=False),
        sa.Column(
            "scanned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_scans_idempotency_key"),
        sa.CheckConstraint("aggregate_score BETWEEN 0 AND 100", name="chk_scans_aggregate_score"),
        _check_in("tier", TIER_VALUES, "chk_scans_tier"),
        _check_in("source", SCAN_SOURCE_VALUES, "chk_scans_source"),
    )
    op.create_index(
        "idx_scans_catalog_item_id_scanned_at", "scans", ["catalog_item_id", "scanned_at"]
    )
    op.create_index("idx_scans_tier", "scans", ["tier"])

    # ── findings ──────────────────────────────────────────────────────────
    op.create_table(
        "findings",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_uuid_v7()")
        ),
        sa.Column(
            "scan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("scans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rule_id", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("sub_score", sa.String(20), nullable=False),
        sa.Column("penalty", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status_at_scan", sa.String(20), nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("line_start", sa.Integer, nullable=False),
        sa.Column("line_end", sa.Integer, nullable=True),
        sa.Column("matched_content_sha256", sa.String(64), nullable=False),
        sa.Column("remediation_link", sa.String(500), nullable=False),
        sa.Column("rubric_version", sa.String(40), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        _check_in("severity", SEVERITY_VALUES, "chk_findings_severity"),
        _check_in("sub_score", SUB_SCORE_VALUES, "chk_findings_sub_score"),
        _check_in("status_at_scan", STATUS_AT_SCAN_VALUES, "chk_findings_status_at_scan"),
        sa.CheckConstraint("penalty BETWEEN 0 AND 40", name="chk_findings_penalty"),
    )
    op.create_index("idx_findings_scan_id", "findings", ["scan_id"])
    op.create_index("idx_findings_rule_id", "findings", ["rule_id"])
    op.create_index("idx_findings_sub_score_severity", "findings", ["sub_score", "severity"])

    # ── vendor_verifications ──────────────────────────────────────────────
    op.create_table(
        "vendor_verifications",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_uuid_v7()")
        ),
        sa.Column(
            "catalog_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("catalog_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash_sha256", sa.String(64), nullable=False),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_github_user", sa.String(100), nullable=True),
        sa.Column("state", sa.String(20), nullable=False, server_default="'pending'"),
        sa.Column("last_drift_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("token_hash_sha256", name="uq_vendor_verifications_token_hash"),
        _check_in("state", VENDOR_VERIFICATION_STATE_VALUES, "chk_vendor_verifications_state"),
    )
    op.create_index(
        "idx_vendor_verifications_catalog_item_state",
        "vendor_verifications",
        ["catalog_item_id", "state"],
    )

    # ── vendor_responses ──────────────────────────────────────────────────
    op.create_table(
        "vendor_responses",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_uuid_v7()")
        ),
        sa.Column(
            "catalog_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("catalog_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "vendor_verification_id",
            UUID(as_uuid=True),
            sa.ForeignKey("vendor_verifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("body_markdown", sa.Text, nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "char_length(body_markdown) BETWEEN 1 AND 2000",
            name="chk_vendor_responses_body_length",
        ),
        sa.CheckConstraint("version >= 1", name="chk_vendor_responses_version"),
    )
    op.create_index(
        "idx_vendor_responses_catalog_item_version_desc",
        "vendor_responses",
        ["catalog_item_id", sa.text("version DESC")],
    )

    # ── item_sources ──────────────────────────────────────────────────────
    op.create_table(
        "item_sources",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_uuid_v7()")
        ),
        sa.Column(
            "catalog_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("catalog_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("registry_id", sa.String(40), nullable=False),
        sa.Column("registry_url", sa.String(500), nullable=False),
        sa.Column("listed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_indexed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "catalog_item_id", "registry_id", name="uq_item_sources_catalog_item_registry"
        ),
        _check_in("registry_id", REGISTRY_ID_VALUES, "chk_item_sources_registry_id"),
    )
    op.create_index("idx_item_sources_registry_id", "item_sources", ["registry_id"])

    # ── rate_limits ───────────────────────────────────────────────────────
    # Composite PK + partial cleanup via periodic procrastinate task (Phase B).
    op.create_table(
        "rate_limits",
        sa.Column("ip_hash", sa.String(64), nullable=False),
        sa.Column("bucket", sa.String(20), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("ip_hash", "bucket", "window_start", name="pk_rate_limits"),
        _check_in("bucket", RATE_LIMIT_BUCKET_VALUES, "chk_rate_limits_bucket"),
    )
    op.create_index("idx_rate_limits_created_at", "rate_limits", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_rate_limits_created_at", table_name="rate_limits")
    op.drop_table("rate_limits")

    op.drop_index("idx_item_sources_registry_id", table_name="item_sources")
    op.drop_table("item_sources")

    op.drop_index("idx_vendor_responses_catalog_item_version_desc", table_name="vendor_responses")
    op.drop_table("vendor_responses")

    op.drop_index("idx_vendor_verifications_catalog_item_state", table_name="vendor_verifications")
    op.drop_table("vendor_verifications")

    op.drop_index("idx_findings_sub_score_severity", table_name="findings")
    op.drop_index("idx_findings_rule_id", table_name="findings")
    op.drop_index("idx_findings_scan_id", table_name="findings")
    op.drop_table("findings")

    op.drop_index("idx_scans_tier", table_name="scans")
    op.drop_index("idx_scans_catalog_item_id_scanned_at", table_name="scans")
    op.drop_table("scans")

    op.drop_index("idx_catalog_items_active", table_name="catalog_items")
    op.drop_index("idx_catalog_items_popularity_tier", table_name="catalog_items")
    op.drop_index("idx_catalog_items_kind", table_name="catalog_items")
    op.drop_table("catalog_items")
