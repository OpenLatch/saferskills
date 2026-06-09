"""add agent-scan subsystem (I-5.5)

Revision ID: 0019_agent_scan
Revises: 0018_scan_install_spec
Create Date: 2026-06-09

I-5.5 Agent Scan (D-5.5-02). Two generated schema-backed entities + three
hand-written internal stores + a new rate-limit bucket. The cloud grades raw
agent evidence deterministically (no LLM) and returns a 0-100 behavioral score.

Adds:
- Native enum types `agent_run_status` + `agent_test_verdict` (idempotent
  `DO $$` block — the 0009 race-safe pattern). `tier`/`severity`/`visibility`
  are reused from 0009.
- `agent_runs` (generated `AgentRun`) — the run state machine + report row.
- `agent_findings` (generated `AgentFinding`) — one observed-vulnerable test row.
- `agent_evidence` — internal raw-record store (submitted `agent_scan_result.v1`
  + the exact served signed pack bytes). Per-run, no dedup. CASCADE.
- `agent_run_token_spent` — single-use replay guard for the one-time submit token
  (mirrors `cli_pow_spent`). Keyed by token hash, reaped by expiry sweep — NOT
  run-cascaded.
- `agent_scan_telemetry` — write-only company-level signal (ASN + server-derived
  fingerprint, no raw IP/PII). `agent_run_id` FK is `SET NULL`.
- `chk_rate_limits_bucket` gains `agent_scan_submit` (VARCHAR + CHECK — the
  `rate_limits` table is an internal hand-written store, not a native-enum
  column). Lineage: 0001 -> 0006 -> 0008 -> 0016 -> here.

Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_agent_scan"
down_revision: str | None = "0018_scan_install_spec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# NEW native enum types created by this migration.
_NEW_ENUMS: dict[str, tuple[str, ...]] = {
    "agent_run_status": ("created", "fetched", "submitted", "graded", "published", "aborted"),
    "agent_test_verdict": ("vulnerable", "not_observed", "n_a", "error"),
}

# `rate_limits.bucket` CHECK lineage: 0001 -> 0006 (+artifact_download) ->
# 0008 (+private_lookup) -> 0016 (+cli_scan_submit) -> here (+agent_scan_submit).
_OLD_BUCKETS = (
    "scan_submit",
    "scan_read",
    "item_read",
    "item_list",
    "artifact_download",
    "private_lookup",
    "cli_scan_submit",
)
_NEW_BUCKETS = (*_OLD_BUCKETS, "agent_scan_submit")


def _quoted(values: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _bucket_check(values: Sequence[str]) -> str:
    return f"bucket IN ({_quoted(values)})"


def _enum(name: str) -> postgresql.ENUM:
    """Reference an EXISTING native enum type (created by the DO $$ block above
    for the new ones, or by 0009 for the reused ones) — never (re)create it."""
    return postgresql.ENUM(name=name, create_type=False)


def upgrade() -> None:
    # 1. Native enum types (idempotent — race-safe on multi-machine boot).
    for name, values in _NEW_ENUMS.items():
        op.execute(
            f"DO $$ BEGIN "
            f"IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{name}') THEN "
            f"CREATE TYPE {name} AS ENUM ({_quoted(values)}); "
            f"END IF; END $$"
        )

    # 2. agent_runs (generated AgentRun).
    op.create_table(
        "agent_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "status", _enum("agent_run_status"), nullable=False, server_default=sa.text("'created'")
        ),
        sa.Column("agent_name", sa.String(200), nullable=False),
        sa.Column("runtime", sa.String(32), nullable=False),
        sa.Column("score", sa.Integer, nullable=True),
        sa.Column("band", _enum("tier"), nullable=False, server_default=sa.text("'unscoped'")),
        sa.Column("verdict_label", sa.String(40), nullable=True),
        sa.Column("cap_callout", sa.Text, nullable=True),
        sa.Column("confidence", sa.String(8), nullable=True),
        sa.Column("score_breakdown", postgresql.JSONB, nullable=True),
        sa.Column(
            "trust_labels", postgresql.JSONB, nullable=True, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("pack_id", sa.String(64), nullable=False),
        sa.Column("pack_version", sa.String(32), nullable=False),
        sa.Column(
            "pack_signature_verified", sa.Boolean, nullable=True, server_default=sa.text("false")
        ),
        sa.Column(
            "capabilities_present",
            postgresql.JSONB,
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "capabilities_absent",
            postgresql.JSONB,
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "family_tally", postgresql.JSONB, nullable=True, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "visibility", _enum("visibility"), nullable=False, server_default=sa.text("'public'")
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rubric_version", sa.Text, nullable=False),
        sa.Column("engine_version", sa.Text, nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=False, unique=True),
        sa.Column("share_token", sa.String(64), nullable=True, unique=True),
        sa.Column("nonce", sa.String(64), nullable=False),
        sa.Column("decoy", sa.String(64), nullable=True),
        sa.Column("pack_sha256", sa.String(64), nullable=True),
        sa.Column("pack_signature", sa.String(128), nullable=True),
        sa.Column("pack_key_id", sa.String(64), nullable=True),
        sa.Column("submit_token_sha256", sa.String(64), nullable=True),
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
    )
    op.create_index(
        "idx_agent_runs_expires_at",
        "agent_runs",
        ["expires_at"],
        postgresql_where=sa.text("visibility = 'unlisted'"),
    )

    # 3. agent_findings (generated AgentFinding).
    op.create_table(
        "agent_findings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "agent_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("test_id", sa.String(8), nullable=False),
        sa.Column("severity", _enum("severity"), nullable=False),
        sa.Column("verdict", _enum("agent_test_verdict"), nullable=False),
        sa.Column("family", sa.String(64), nullable=False),
        sa.Column(
            "owasp_refs", postgresql.JSONB, nullable=True, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "atlas_refs", postgresql.JSONB, nullable=True, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "nist_refs", postgresql.JSONB, nullable=True, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("score_delta", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("detection_rule", sa.String(32), nullable=False),
        sa.Column("leaked_canary_slot", sa.String(64), nullable=True),
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
    )
    op.create_index("idx_agent_findings_run_id", "agent_findings", ["agent_run_id"])

    # 4. agent_evidence — internal raw-record store (no JSON Schema, no wire DTO).
    op.create_table(
        "agent_evidence",
        sa.Column(
            "agent_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("result_json", postgresql.JSONB, nullable=True),
        sa.Column("pack_bytes", postgresql.BYTEA, nullable=True),
        sa.Column("byte_size", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # 5. agent_run_token_spent — single-use submit-token ledger (mirrors cli_pow_spent).
    op.create_table(
        "agent_run_token_spent",
        sa.Column("token_sha256", sa.String(64), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_agent_run_token_spent_expires_at", "agent_run_token_spent", ["expires_at"])

    # 6. agent_scan_telemetry — write-only company-level signal (no raw IP/PII).
    op.create_table(
        "agent_scan_telemetry",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "agent_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("asn", sa.String(16), nullable=True),
        sa.Column("as_org", sa.String(255), nullable=True),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("fingerprint", postgresql.JSONB, nullable=True),
        sa.Column("opted_out", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_agent_scan_telemetry_created", "agent_scan_telemetry", ["created_at"])

    # 7. rate_limits CHECK += agent_scan_submit (drop + recreate).
    op.drop_constraint("chk_rate_limits_bucket", "rate_limits", type_="check")
    op.create_check_constraint("chk_rate_limits_bucket", "rate_limits", _bucket_check(_NEW_BUCKETS))


def downgrade() -> None:
    op.drop_constraint("chk_rate_limits_bucket", "rate_limits", type_="check")
    op.create_check_constraint("chk_rate_limits_bucket", "rate_limits", _bucket_check(_OLD_BUCKETS))

    op.drop_index("idx_agent_scan_telemetry_created", table_name="agent_scan_telemetry")
    op.drop_table("agent_scan_telemetry")

    op.drop_index("idx_agent_run_token_spent_expires_at", table_name="agent_run_token_spent")
    op.drop_table("agent_run_token_spent")

    op.drop_table("agent_evidence")

    op.drop_index("idx_agent_findings_run_id", table_name="agent_findings")
    op.drop_table("agent_findings")

    op.drop_index("idx_agent_runs_expires_at", table_name="agent_runs")
    op.drop_table("agent_runs")

    for name in _NEW_ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {name}")
