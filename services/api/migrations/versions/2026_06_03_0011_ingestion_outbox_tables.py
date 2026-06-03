"""ingestion outbox + cursor + admin tables + item_sources.status ALTER

Revision ID: 0011_ingestion_outbox_tables
Revises: 0010_catalog_full_projection
Create Date: 2026-06-03

I-04 Phase A. Creates the outbox + cursor + B2B-funnel + admin tables and ALTERs
the existing item_sources table to add `status`. Does NOT create item_sources
(it exists since 0001). Does NOT install the Procrastinate schema — that is
applied at startup via the async schema manager under advisory lock 0x5AFE5C13
(app/main.py lifespan), never in a migration; Alembic owns the SaferSkills
tables, Procrastinate owns the procrastinate_* tables.

ingestion_events + merge_candidates back GENERATED ORM models
(app/models/generated/); the column definitions here mirror those models exactly.
crawler_cursors / access_log / admin_audit_log / popularity_formulas are internal
hand-written models (no JSON-Schema source).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_ingestion_outbox_tables"
down_revision: str | None = "0010_catalog_full_projection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SOURCE_ENUM_VALUES: tuple[str, ...] = (
    "github_skills",
    "github_topics",
    "mcp_registry",
    "npm",
    "pypi",
    "mcp_so",
    "smithery",
    "glama",
    "pulsemcp",
    "clawhub",
    "skillsmp",
    "skills_sh",
    "claudeskills_info",
    "skillhub_club",
)
SOURCE_STATUS_VALUES = ("active", "paused", "blocked", "disabled")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    # 1. ingestion_events — the outbox log (mirrors app/models/generated/ingestion_event.py).
    op.create_table(
        "ingestion_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_id", sa.String(500), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("body_sha256", sa.String(64), nullable=False),
        sa.Column("etag", sa.String(200), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("from_cache", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("fetch_tier", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_reason", sa.String(50), nullable=True),
    )
    op.create_check_constraint(
        "chk_ingestion_events_source",
        "ingestion_events",
        f"source IN ({_quoted(SOURCE_ENUM_VALUES)})",
    )
    op.create_check_constraint(
        "chk_ingestion_events_status", "ingestion_events", "http_status >= 0 AND http_status <= 599"
    )
    op.create_check_constraint(
        "chk_ingestion_events_tier", "ingestion_events", "fetch_tier IN (0,1,2,3)"
    )
    # Indexes declared on the generated model:
    op.create_index("idx_ingestion_events_source", "ingestion_events", ["source"])
    op.create_index(
        "idx_ingestion_events_unapplied",
        "ingestion_events",
        ["applied_at"],
        postgresql_where=sa.text("applied_at IS NULL"),
    )
    # Extra query indexes (expression/composite — migration-only):
    op.create_index(
        "idx_ingestion_events_source_fetched_desc",
        "ingestion_events",
        ["source", sa.text("fetched_at DESC")],
    )
    op.create_index(
        "idx_ingestion_events_source_sourceid",
        "ingestion_events",
        ["source", "source_id", sa.text("fetched_at DESC")],
    )

    # 2. item_sources — ALTER ONLY (table exists since 0001). Add `status`.
    op.add_column(
        "item_sources",
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'active'")),
    )
    op.create_check_constraint(
        "chk_item_sources_status", "item_sources", f"status IN ({_quoted(SOURCE_STATUS_VALUES)})"
    )
    op.create_index("idx_item_sources_status", "item_sources", ["status"])
    op.create_index(
        "idx_item_sources_catalog_item_id_status",
        "item_sources",
        ["catalog_item_id", "status"],
    )

    # 3. merge_candidates — manual-review queue (mirrors generated/merge_candidate.py).
    op.create_table(
        "merge_candidates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("left_artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("right_artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rapidfuzz_score", sa.Float(precision=24), nullable=False),
        sa.Column("jaro_winkler_score", sa.Float(precision=24), nullable=False),
        sa.Column(
            "signals", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("decided_by", sa.String(20), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=True),
        sa.ForeignKeyConstraint(["left_artifact_id"], ["catalog_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["right_artifact_id"], ["catalog_items.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "left_artifact_id < right_artifact_id", name="chk_merge_candidates_ordered"
        ),
        sa.UniqueConstraint(
            "left_artifact_id", "right_artifact_id", name="uq_merge_candidates_pair"
        ),
    )
    op.create_check_constraint(
        "chk_merge_candidates_status",
        "merge_candidates",
        "status IN ('pending','merged','rejected')",
    )
    op.create_index(
        "idx_merge_candidates_pending",
        "merge_candidates",
        ["status"],
        postgresql_where=sa.text("status = 'pending'"),
    )

    # 4. crawler_cursors — per-source resume marker (hand-written model).
    op.create_table(
        "crawler_cursors",
        sa.Column("source", sa.String(50), primary_key=True),
        sa.Column(
            "cursor_value",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_successful_cycle_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempted_cycle_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "consecutive_failure_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("status_reason", sa.String(500), nullable=True),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status_contact", sa.String(200), nullable=True),
    )
    op.create_check_constraint(
        "chk_crawler_cursors_source",
        "crawler_cursors",
        f"source IN ({_quoted(SOURCE_ENUM_VALUES)})",
    )
    op.create_check_constraint(
        "chk_crawler_cursors_status",
        "crawler_cursors",
        f"status IN ({_quoted(SOURCE_STATUS_VALUES)})",
    )

    # 5. access_log — B2B intel signal (write-only at I-04; I-06 reads). /24-/48 redacted IP.
    op.create_table(
        "access_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "ts", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("item_content_hash", sa.String(64), nullable=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("http_referer_host", sa.String(200), nullable=True),
    )
    op.create_check_constraint(
        "chk_access_log_action",
        "access_log",
        "action IN ('item_view','catalog_search','catalog_filter','install_copy','badge_fetch','sources_page_view')",
    )
    op.create_index("idx_access_log_ts_desc", "access_log", [sa.text("ts DESC")])
    op.create_index(
        "idx_access_log_content_hash_ts",
        "access_log",
        ["item_content_hash", sa.text("ts DESC")],
        postgresql_where=sa.text("item_content_hash IS NOT NULL"),
    )

    # 6. admin_audit_log — every admin endpoint mutation (Phase C admin CLI).
    op.create_table(
        "admin_audit_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "ts", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("actor_admin_key_fp", sa.String(20), nullable=False),
        sa.Column("target", sa.String(500), nullable=True),
        sa.Column("before", postgresql.JSONB(), nullable=True),
        sa.Column("after", postgresql.JSONB(), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
    )
    op.create_index("idx_admin_audit_log_ts_desc", "admin_audit_log", [sa.text("ts DESC")])
    op.create_index(
        "idx_admin_audit_log_action_ts", "admin_audit_log", ["action", sa.text("ts DESC")]
    )

    # 7. popularity_formulas — version-locked weights (consumed Phase C).
    op.create_table(
        "popularity_formulas",
        sa.Column("version", sa.String(20), primary_key=True),
        sa.Column("weights", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.execute(
        """
        INSERT INTO popularity_formulas (version, weights, active) VALUES (
            'popularity_v1',
            '{"starsTerm": 0.45, "velocityTerm": 0.20, "downloadsTerm": 0.20, "crossRegistryTerm": 0.10, "recencyTerm": 0.05}'::jsonb,
            true
        )
        """
    )

    # 8. Seed one crawler_cursors row per source (status='active').
    for s in SOURCE_ENUM_VALUES:
        op.execute(sa.text("INSERT INTO crawler_cursors (source) VALUES (:s)").bindparams(s=s))


def downgrade() -> None:
    op.drop_index("idx_admin_audit_log_action_ts", table_name="admin_audit_log")
    op.drop_index("idx_admin_audit_log_ts_desc", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")

    op.drop_index("idx_access_log_content_hash_ts", table_name="access_log")
    op.drop_index("idx_access_log_ts_desc", table_name="access_log")
    op.drop_table("access_log")

    op.drop_table("crawler_cursors")
    op.drop_table("popularity_formulas")

    op.drop_index("idx_merge_candidates_pending", table_name="merge_candidates")
    op.drop_table("merge_candidates")

    # item_sources is ALTER-only (predates this migration) — reverse just the status additions.
    op.drop_index("idx_item_sources_catalog_item_id_status", table_name="item_sources")
    op.drop_index("idx_item_sources_status", table_name="item_sources")
    op.drop_constraint("chk_item_sources_status", "item_sources", type_="check")
    op.drop_column("item_sources", "status")

    op.drop_index("idx_ingestion_events_source_sourceid", table_name="ingestion_events")
    op.drop_index("idx_ingestion_events_source_fetched_desc", table_name="ingestion_events")
    op.drop_index("idx_ingestion_events_unapplied", table_name="ingestion_events")
    op.drop_index("idx_ingestion_events_source", table_name="ingestion_events")
    op.drop_table("ingestion_events")
