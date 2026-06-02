# DO NOT EDIT — regenerate via: pnpm run generate (scripts/generate_sqlalchemy_models.py)
"""SQLAlchemy declarative base re-export + shared PostgreSQL native enum types.

The value tuples below are the closed-set source of truth — they mirror the
native PG enum types (and their predecessor CHECK constraints) in the Alembic
migration chain. `create_type=False`: this generator never emits DDL; the
migrations own every `CREATE TYPE … AS ENUM`.

`Base` is re-exported from `app.models.base` so generated models and the
hand-written internal models (item_source, rate_limit, upload_file,
artifact_blob, scan_event) share one `Base.metadata`.
"""

import sqlalchemy as sa

from app.models.base import Base

__all__ = [
    "KIND_VALUES",
    "POPULARITY_TIER_VALUES",
    "SCAN_RUN_STATUS_VALUES",
    "SCAN_SOURCE_VALUES",
    "SEVERITY_VALUES",
    "SOURCE_KIND_VALUES",
    "STATUS_AT_SCAN_VALUES",
    "SUB_SCORE_VALUES",
    "TIER_VALUES",
    "VENDOR_VERIFICATION_STATE_VALUES",
    "VISIBILITY_VALUES",
    "Base",
    "kind_enum",
    "popularity_tier_enum",
    "scan_run_status_enum",
    "scan_source_enum",
    "severity_enum",
    "source_kind_enum",
    "status_at_scan_enum",
    "sub_score_enum",
    "tier_enum",
    "vendor_verification_state_enum",
    "visibility_enum",
]

# PostgreSQL native enum `kind`: PRD §2.2 artifact taxonomy.
KIND_VALUES = (
    "skill",
    "mcp_server",
    "hook",
    "plugin",
    "rules",
)
kind_enum = sa.Enum(
    *KIND_VALUES,
    name="kind",
    native_enum=True,
    create_type=False,
    create_constraint=False,
)
# PostgreSQL native enum `popularity_tier`: PRD §6.2 scan-tier assignment.
POPULARITY_TIER_VALUES = (
    "indexed",
    "lite",
    "deep",
    "on_demand",
)
popularity_tier_enum = sa.Enum(
    *POPULARITY_TIER_VALUES,
    name="popularity_tier",
    native_enum=True,
    create_type=False,
    create_constraint=False,
)
# PostgreSQL native enum `scan_run_status`: Repo-scan run lifecycle status.
SCAN_RUN_STATUS_VALUES = (
    "pending",
    "running",
    "completed",
    "failed",
)
scan_run_status_enum = sa.Enum(
    *SCAN_RUN_STATUS_VALUES,
    name="scan_run_status",
    native_enum=True,
    create_type=False,
    create_constraint=False,
)
# PostgreSQL native enum `scan_source`: How the scan was triggered.
SCAN_SOURCE_VALUES = (
    "submission",
    "ingestion",
    "rescan_drift",
    "rescan_appeal",
)
scan_source_enum = sa.Enum(
    *SCAN_SOURCE_VALUES,
    name="scan_source",
    native_enum=True,
    create_type=False,
    create_constraint=False,
)
# PostgreSQL native enum `severity`: 5-tier severity ladder per D-02.
SEVERITY_VALUES = (
    "info",
    "low",
    "medium",
    "high",
    "critical",
)
severity_enum = sa.Enum(
    *SEVERITY_VALUES,
    name="severity",
    native_enum=True,
    create_type=False,
    create_constraint=False,
)
# PostgreSQL native enum `source_kind`: Origin of the scanned bytes (I-3.5).
SOURCE_KIND_VALUES = (
    "github",
    "upload",
)
source_kind_enum = sa.Enum(
    *SOURCE_KIND_VALUES,
    name="source_kind",
    native_enum=True,
    create_type=False,
    create_constraint=False,
)
# PostgreSQL native enum `status_at_scan`: Rule status when finding emitted (D-14).
STATUS_AT_SCAN_VALUES = (
    "shadow",
    "active",
)
status_at_scan_enum = sa.Enum(
    *STATUS_AT_SCAN_VALUES,
    name="status_at_scan",
    native_enum=True,
    create_type=False,
    create_constraint=False,
)
# PostgreSQL native enum `sub_score`: 5-axis sub-score per D-01.
SUB_SCORE_VALUES = (
    "security",
    "supply_chain",
    "maintenance",
    "transparency",
    "community",
)
sub_score_enum = sa.Enum(
    *SUB_SCORE_VALUES,
    name="sub_score",
    native_enum=True,
    create_type=False,
    create_constraint=False,
)
# PostgreSQL native enum `tier`: Aggregate scan-result tier.
TIER_VALUES = (
    "green",
    "yellow",
    "orange",
    "red",
    "unscoped",
)
tier_enum = sa.Enum(
    *TIER_VALUES,
    name="tier",
    native_enum=True,
    create_type=False,
    create_constraint=False,
)
# PostgreSQL native enum `vendor_verification_state`: Vendor verification lifecycle.
VENDOR_VERIFICATION_STATE_VALUES = (
    "pending",
    "verified",
    "expired",
    "revoked",
)
vendor_verification_state_enum = sa.Enum(
    *VENDOR_VERIFICATION_STATE_VALUES,
    name="vendor_verification_state",
    native_enum=True,
    create_type=False,
    create_constraint=False,
)
# PostgreSQL native enum `visibility`: Listing posture (I-3.5).
VISIBILITY_VALUES = (
    "public",
    "unlisted",
)
visibility_enum = sa.Enum(
    *VISIBILITY_VALUES,
    name="visibility",
    native_enum=True,
    create_type=False,
    create_constraint=False,
)
