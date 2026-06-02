"""native enum types — convert VARCHAR+CHECK enum columns to PG native enums.

Revision ID: 0009_native_enum_types
Revises: 0008_add_upload_and_visibility
Create Date: 2026-06-02

I-04 Phase A0 (codegen port). The generated SQLAlchemy models
(`app/models/generated/`) declare enum columns as **native PostgreSQL enum
types** (`sa.Enum(*VALUES, native_enum=True, create_type=False)`), mirroring
openlatch-platform's generator. The migration chain 0001-0008 created those
columns as `VARCHAR(20)` + a `CHECK (col IN (...))` constraint. This migration
creates the native enum types and converts every generated enum column to its
native type, dropping the now-redundant CHECK constraints.

The enum value tuples below are the single closed-set source of truth shared
with `app/models/generated/_base.py` (`KIND_VALUES`, `TIER_VALUES`, …) and the
original CHECK constraints (migrations 0001 / 0007 / 0008).

Reversible: `downgrade()` converts each column back to `VARCHAR(20)`, restores
its CHECK constraint, and drops the enum types. `item_sources.registry_id` and
`rate_limits.bucket` are intentionally NOT converted — they back internal
hand-written models with no generated native-enum column, so they stay
VARCHAR+CHECK.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic.
revision: str = "0009_native_enum_types"
down_revision: str | None = "0008_add_upload_and_visibility"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Native enum type name -> closed value set (mirrors generated/_base.py).
ENUM_TYPES: dict[str, tuple[str, ...]] = {
    "kind": ("skill", "mcp_server", "hook", "plugin", "rules"),
    "popularity_tier": ("indexed", "lite", "deep", "on_demand"),
    "tier": ("green", "yellow", "orange", "red", "unscoped"),
    "scan_source": ("submission", "ingestion", "rescan_drift", "rescan_appeal"),
    "scan_run_status": ("pending", "running", "completed", "failed"),
    "severity": ("info", "low", "medium", "high", "critical"),
    "sub_score": ("security", "supply_chain", "maintenance", "transparency", "community"),
    "status_at_scan": ("shadow", "active"),
    "vendor_verification_state": ("pending", "verified", "expired", "revoked"),
    "visibility": ("public", "unlisted"),
    "source_kind": ("github", "upload"),
}

# (table, column, enum_type, check_constraint_name, server_default | None)
# server_default is the bare enum value to restore after the type swap.
CONVERSIONS: tuple[tuple[str, str, str, str, str | None], ...] = (
    ("catalog_items", "kind", "kind", "chk_catalog_items_kind", None),
    (
        "catalog_items",
        "popularity_tier",
        "popularity_tier",
        "chk_catalog_items_popularity_tier",
        None,
    ),
    ("catalog_items", "visibility", "visibility", "chk_catalog_items_visibility", "public"),
    ("catalog_items", "source_kind", "source_kind", "chk_catalog_items_source_kind", "github"),
    ("scans", "tier", "tier", "chk_scans_tier", None),
    ("scans", "source", "scan_source", "chk_scans_source", None),
    ("findings", "severity", "severity", "chk_findings_severity", None),
    ("findings", "sub_score", "sub_score", "chk_findings_sub_score", None),
    ("findings", "status_at_scan", "status_at_scan", "chk_findings_status_at_scan", None),
    ("scan_runs", "repo_tier", "tier", "chk_scan_runs_repo_tier", "unscoped"),
    ("scan_runs", "source", "scan_source", "chk_scan_runs_source", None),
    ("scan_runs", "status", "scan_run_status", "chk_scan_runs_status", "pending"),
    ("scan_runs", "visibility", "visibility", "chk_scan_runs_visibility", "public"),
    ("scan_runs", "source_kind", "source_kind", "chk_scan_runs_source_kind", "github"),
    (
        "vendor_verifications",
        "state",
        "vendor_verification_state",
        "chk_vendor_verifications_state",
        "pending",
    ),
)


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    # 1. Create the native enum types (idempotent — race-safe on multi-machine boot).
    for name, values in ENUM_TYPES.items():
        op.execute(
            f"DO $$ BEGIN "
            f"IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{name}') THEN "
            f"CREATE TYPE {name} AS ENUM ({_quoted(values)}); "
            f"END IF; END $$"
        )

    # The partial index `idx_scan_runs_expires_at WHERE visibility = 'unlisted'`
    # (migration 0008) references visibility in its predicate; ALTER COLUMN TYPE
    # can't re-evaluate a predicate mid-swap ("functions in index predicate must
    # be marked IMMUTABLE"). Drop it, convert, recreate.
    op.drop_index("idx_scan_runs_expires_at", table_name="scan_runs")

    # 2. Convert each column: drop the redundant CHECK, drop the text default,
    #    swap the type via an explicit cast, then restore the default as the enum.
    for table, col, enum_type, check, default in CONVERSIONS:
        op.drop_constraint(check, table, type_="check")
        if default is not None:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {col} DROP DEFAULT")
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {col} "
            f"TYPE {enum_type} USING {col}::text::{enum_type}"
        )
        if default is not None:
            op.execute(
                f"ALTER TABLE {table} ALTER COLUMN {col} SET DEFAULT '{default}'::{enum_type}"
            )

    op.create_index(
        "idx_scan_runs_expires_at",
        "scan_runs",
        ["expires_at"],
        postgresql_where=sa.text("visibility = 'unlisted'"),
    )


def downgrade() -> None:
    # Drop the visibility-predicated partial index before swapping the column
    # type back (symmetric with upgrade).
    op.drop_index("idx_scan_runs_expires_at", table_name="scan_runs")

    # Convert every column back to VARCHAR(20) + CHECK first, so no column still
    # references an enum type when we drop the types.
    for table, col, enum_type, check, default in reversed(CONVERSIONS):
        if default is not None:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {col} DROP DEFAULT")
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {col} TYPE VARCHAR(20) USING {col}::text")
        if default is not None:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {col} SET DEFAULT '{default}'")
        op.create_check_constraint(check, table, f"{col} IN ({_quoted(ENUM_TYPES[enum_type])})")

    op.create_index(
        "idx_scan_runs_expires_at",
        "scan_runs",
        ["expires_at"],
        postgresql_where=sa.text("visibility = 'unlisted'"),
    )

    for name in ENUM_TYPES:
        op.execute(f"DROP TYPE IF EXISTS {name}")
