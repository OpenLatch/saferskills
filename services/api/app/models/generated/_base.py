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
    "AGENT_RUN_STATUS_VALUES",
    "AGENT_TEST_VERDICT_VALUES",
    "AVAILABILITY_VALUES",
    "KIND_VALUES",
    "POPULARITY_RANK_TIER_VALUES",
    "POPULARITY_TIER_VALUES",
    "QUALITY_TIER_VALUES",
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
    "agent_run_status_enum",
    "agent_test_verdict_enum",
    "availability_enum",
    "kind_enum",
    "popularity_rank_tier_enum",
    "popularity_tier_enum",
    "quality_tier_enum",
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

# PostgreSQL native enum `agent_run_status`: Agent-scan run lifecycle status (I-5.5).
AGENT_RUN_STATUS_VALUES = (
    "created",
    "fetched",
    "submitted",
    "graded",
    "published",
    "aborted",
)
agent_run_status_enum = sa.Enum(
    *AGENT_RUN_STATUS_VALUES,
    name="agent_run_status",
    native_enum=True,
    create_type=False,
    create_constraint=False,
)
# PostgreSQL native enum `agent_test_verdict`: Per-test outcome of a behavioral agent test (I-5.5).
AGENT_TEST_VERDICT_VALUES = (
    "vulnerable",
    "not_observed",
    "n_a",
    "error",
)
agent_test_verdict_enum = sa.Enum(
    *AGENT_TEST_VERDICT_VALUES,
    name="agent_test_verdict",
    native_enum=True,
    create_type=False,
    create_constraint=False,
)
# PostgreSQL native enum `availability`: Three-state catalog availability (I-04 D-04-17).
AVAILABILITY_VALUES = (
    "available",
    "unavailable",
    "archived",
)
availability_enum = sa.Enum(
    *AVAILABILITY_VALUES,
    name="availability",
    native_enum=True,
    create_type=False,
    create_constraint=False,
)
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
# PostgreSQL native enum `popularity_rank_tier`: Rank-based popularity bucket, distinct from the scan-tier (I-04 D-04-13).
POPULARITY_RANK_TIER_VALUES = (
    "top500",
    "top5k",
    "long_tail",
)
popularity_rank_tier_enum = sa.Enum(
    *POPULARITY_RANK_TIER_VALUES,
    name="popularity_rank_tier",
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
# PostgreSQL native enum `quality_tier`: Soft quality gate (I-04 D-04-19).
QUALITY_TIER_VALUES = (
    "high",
    "medium",
    "low",
    "empty",
)
quality_tier_enum = sa.Enum(
    *QUALITY_TIER_VALUES,
    name="quality_tier",
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
    "rescan_rules",
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
