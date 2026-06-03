"""catalog full projection + FTS + pg_trgm + source-enum rename + authors

Revision ID: 0010_catalog_full_projection
Revises: 0009_native_enum_types
Create Date: 2026-06-03

I-04 Phase A. Adds the genuinely-new catalog_items columns from the extended
schemas/catalog-item.schema.json — all additive, never altering an existing
column, never re-adding columns shipped by 0003/0004/0008. The three new enum
columns (availability, quality_tier, popularity_rank_tier) are NATIVE PG enum
types (consistent with 0009 / the codegen contract — registered in KNOWN_ENUMS),
created idempotently with the same DO $$ … $$ guard 0009 uses.

Also: Postgres FTS tsvector (generated column) + GIN index, pg_trgm extension +
trigram index for the existing /items?q= route (D-04-32 — swaps the ILIKE query
for FTS; does NOT build a route), the source-enum rename on
item_sources.registry_id (D-04-25, PRESERVING the I-3.5 values), and the authors
table + author_summary materialized view (refresh task ships Phase C).

scan_depth / last_deep_scan_at / last_lite_scan_at are intentionally deferred to
the Phase C migration — they are consumed only by the Phase C auto-scan triggers
and adding them now would mean editing the generated scan_runs/catalog_items wire
schemas for no Phase-A consumer (scope discipline).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_catalog_full_projection"
down_revision: str | None = "0009_native_enum_types"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# New native enum types (mirror KNOWN_ENUMS in generate_sqlalchemy_models.py +
# the *_VALUES tuples in app/models/generated/_base.py).
NEW_ENUM_TYPES: dict[str, tuple[str, ...]] = {
    "availability": ("available", "unavailable", "archived"),
    "quality_tier": ("high", "medium", "low", "empty"),
    "popularity_rank_tier": ("top500", "top5k", "long_tail"),
}

# Source-enum after the I-04 rename — the 14 crawled sources + the 3 I-3.5 values.
REGISTRY_ID_VALUES_NEW: tuple[str, ...] = (
    "github_skills",
    "github_topics",
    "mcp_registry",
    "npm",
    "pypi",
    "clawhub",
    "skillsmp",
    "skills_sh",
    "claudeskills_info",
    "skillhub_club",
    "mcp_so",
    "smithery",
    "glama",
    "pulsemcp",
    "upload",
    "user_submission",
    "vendor_verified",
)
# Pre-I-04 value set (for the reversible downgrade — matches 0001 + the 0008 `upload` add).
REGISTRY_ID_VALUES_OLD: tuple[str, ...] = (
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
    "upload",
)


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _pg_enum(name: str) -> postgresql.ENUM:
    """Reference an already-created PG enum type (the DO $$ block owns CREATE TYPE)."""
    return postgresql.ENUM(*NEW_ENUM_TYPES[name], name=name, create_type=False)


def upgrade() -> None:
    # 1. Extensions + native enum types (idempotent — race-safe on multi-machine boot).
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for name, values in NEW_ENUM_TYPES.items():
        op.execute(
            f"DO $$ BEGIN "
            f"IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{name}') THEN "
            f"CREATE TYPE {name} AS ENUM ({_quoted(values)}); "
            f"END IF; END $$"
        )

    # 2. New catalog_items columns (NEW only — never re-add 0003/0004/0008 columns).
    op.add_column(
        "catalog_items",
        sa.Column(
            "availability",
            _pg_enum("availability"),
            nullable=False,
            server_default=sa.text("'available'::availability"),
        ),
    )
    op.add_column(
        "catalog_items",
        sa.Column(
            "quality_tier",
            _pg_enum("quality_tier"),
            nullable=False,
            server_default=sa.text("'medium'::quality_tier"),
        ),
    )
    op.add_column(
        "catalog_items",
        sa.Column(
            "quality_signals",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "catalog_items",
        sa.Column("fork_of_repo_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_catalog_items_fork_of",
        "catalog_items",
        "catalog_items",
        ["fork_of_repo_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "catalog_items",
        sa.Column(
            "popularity_breakdown",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "catalog_items",
        sa.Column(
            "kind_signals",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    # Column names are the codegen-derived snake_case of the schema fields
    # `consecutive404Count` / `lastSeen200At` (camel_to_snake groups the digits):
    # consecutive404_count / last_seen200_at — they MUST match the generated model.
    op.add_column(
        "catalog_items",
        sa.Column(
            "consecutive404_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "catalog_items",
        sa.Column("last_seen200_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "catalog_items",
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill pushed_at from the metadata jsonb where present (minimal data expected).
    op.execute(
        "UPDATE catalog_items SET pushed_at = (metadata->>'pushed_at')::timestamptz "
        "WHERE metadata ? 'pushed_at' AND metadata->>'pushed_at' IS NOT NULL"
    )
    op.add_column(
        "catalog_items",
        sa.Column(
            "popularity_rank_tier",
            _pg_enum("popularity_rank_tier"),
            nullable=False,
            server_default=sa.text("'long_tail'::popularity_rank_tier"),
        ),
    )

    # 3. FTS tsvector (generated column) + GIN index.
    op.execute(
        "ALTER TABLE catalog_items ADD COLUMN search_vector tsvector "
        "GENERATED ALWAYS AS ("
        "setweight(to_tsvector('english', coalesce(display_name,'')), 'A') || "
        "setweight(to_tsvector('english', coalesce(github_org,'') || ' ' || coalesce(github_repo,'')), 'B') || "
        "setweight(to_tsvector('english', coalesce(metadata->>'description','')), 'C')"
        ") STORED"
    )
    op.create_index(
        "idx_catalog_items_search_vector",
        "catalog_items",
        ["search_vector"],
        postgresql_using="gin",
    )

    # 4. pg_trgm typeahead index on display_name.
    op.execute(
        "CREATE INDEX idx_catalog_items_name_trgm ON catalog_items "
        "USING gin (display_name gin_trgm_ops)"
    )

    # 5. Supporting indexes for the new columns (idempotent).
    op.create_index(
        "idx_catalog_items_popularity_rank_tier", "catalog_items", ["popularity_rank_tier"]
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_catalog_items_availability "
        "ON catalog_items (availability) WHERE availability != 'available'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_catalog_items_last_seen_200 "
        "ON catalog_items (last_seen200_at) WHERE consecutive404_count > 0"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_catalog_items_kind_quality_arch "
        "ON catalog_items (kind, quality_tier, archived)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_catalog_items_pushed_at "
        "ON catalog_items (pushed_at DESC NULLS LAST)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_catalog_items_popularity_score_desc "
        "ON catalog_items (popularity_score DESC NULLS LAST) WHERE archived = false"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_catalog_items_agent_compatibility "
        "ON catalog_items USING gin (agent_compatibility)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_catalog_items_github_username "
        "ON catalog_items ((metadata->>'github_username'))"
    )

    # 6. Source-enum rename on item_sources.registry_id (D-04-25). PRESERVE the I-3.5 values.
    op.drop_constraint("chk_item_sources_registry_id", "item_sources", type_="check")
    op.execute(
        "UPDATE item_sources SET registry_id = 'github_topics' WHERE registry_id = 'github_topic'"
    )
    op.execute(
        "UPDATE item_sources SET registry_id = 'github_skills' WHERE registry_id = 'anthropics_skills'"
    )
    op.create_check_constraint(
        "chk_item_sources_registry_id",
        "item_sources",
        f"registry_id IN ({_quoted(REGISTRY_ID_VALUES_NEW)})",
    )

    # 7. authors table — github_id nullable with a partial unique index (Codex P0-6).
    op.create_table(
        "authors",
        sa.Column("github_username", sa.String(100), primary_key=True),
        sa.Column("github_id", sa.BigInteger(), nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("display_name", sa.String(200), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_authors_github_id_when_known",
        "authors",
        ["github_id"],
        unique=True,
        postgresql_where=sa.text("github_id IS NOT NULL"),
    )

    # 8. author_summary materialized view (refreshed nightly + on-write by Phase C).
    op.execute(
        """
        CREATE MATERIALIZED VIEW author_summary AS
        SELECT
            metadata->>'github_username' AS github_username,
            COUNT(*) AS item_count,
            COALESCE(AVG(NULLIF((metadata->>'aggregate_score')::float, 0)), 0) AS avg_score,
            COUNT(*) FILTER (WHERE (metadata->>'aggregate_score')::float < 40) AS red_count,
            BOOL_OR(
                (metadata->>'aggregate_score')::float < 40
                AND (metadata->>'scanned_at')::timestamptz > now() - interval '90 days'
            ) AS has_recent_red,
            now() AS refreshed_at
        FROM catalog_items
        WHERE metadata->>'github_username' IS NOT NULL
        GROUP BY metadata->>'github_username'
        """
    )
    op.create_index(
        "idx_author_summary_username", "author_summary", ["github_username"], unique=True
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS author_summary")
    op.drop_index("uq_authors_github_id_when_known", table_name="authors")
    op.drop_table("authors")

    # Restore the pre-I-04 source-enum (best-effort; rows with new-only names fail the old CHECK).
    op.drop_constraint("chk_item_sources_registry_id", "item_sources", type_="check")
    op.execute(
        "UPDATE item_sources SET registry_id = 'anthropics_skills' WHERE registry_id = 'github_skills'"
    )
    op.execute(
        "UPDATE item_sources SET registry_id = 'github_topic' WHERE registry_id = 'github_topics'"
    )
    op.execute(
        "DELETE FROM item_sources WHERE registry_id IN ('skills_sh','claudeskills_info','skillhub_club')"
    )
    op.create_check_constraint(
        "chk_item_sources_registry_id",
        "item_sources",
        f"registry_id IN ({_quoted(REGISTRY_ID_VALUES_OLD)})",
    )

    for idx in (
        "idx_catalog_items_github_username",
        "idx_catalog_items_agent_compatibility",
        "idx_catalog_items_popularity_score_desc",
        "idx_catalog_items_pushed_at",
        "idx_catalog_items_kind_quality_arch",
        "idx_catalog_items_last_seen_200",
        "idx_catalog_items_availability",
        "idx_catalog_items_name_trgm",
    ):
        op.execute(f"DROP INDEX IF EXISTS {idx}")
    op.drop_index("idx_catalog_items_popularity_rank_tier", table_name="catalog_items")
    op.drop_index("idx_catalog_items_search_vector", table_name="catalog_items")
    op.execute("ALTER TABLE catalog_items DROP COLUMN IF EXISTS search_vector")

    op.drop_column("catalog_items", "popularity_rank_tier")
    op.drop_column("catalog_items", "pushed_at")
    op.drop_column("catalog_items", "last_seen200_at")
    op.drop_column("catalog_items", "consecutive404_count")
    op.drop_column("catalog_items", "kind_signals")
    op.drop_column("catalog_items", "popularity_breakdown")
    op.drop_constraint("fk_catalog_items_fork_of", "catalog_items", type_="foreignkey")
    op.drop_column("catalog_items", "fork_of_repo_id")
    op.drop_column("catalog_items", "quality_signals")
    op.drop_column("catalog_items", "quality_tier")
    op.drop_column("catalog_items", "availability")

    for name in NEW_ENUM_TYPES:
        op.execute(f"DROP TYPE IF EXISTS {name}")
    # pg_trgm left installed (other features may rely on it); harmless if it stays.
