"""widen chk_ingestion_runs_trigger to include 'reconcile'

Revision ID: 0025_widen_ingestion_trigger
Revises: 0024_skill_compat_all_agents
Create Date: 2026-06-21

Keystone fix for the staging ingestion-worker error flood. The overdue reconciler
(`ingestion_overdue_reconciler`, PR #129) re-defers a missed daily cron tick with
`trigger="reconcile"` (`tasks.defer_source_cycle`). But migration `0013` created
`chk_ingestion_runs_trigger` allowing only `('scheduled','manual','force')` — no
migration widened it for `reconcile`. So every reconcile `record_run_started` INSERT
violated the CHECK, was swallowed (best-effort), and wrote NO run-record.
`reconcile_overdue_sources` decides "overdue" from `max(ingestion_runs.started_at)`;
with no record ever written, every daily-cron source looked perpetually overdue and was
re-fired every 15 min instead of once/day (~96x over-firing), flooding the worker with
`run_record_start_failed` warnings.

Widening the CHECK lets the first reconcile tick write a run-record, after which
`reconcile_overdue_sources` sees the attempt and stops the 15-min loop until the next
real cron tick. Self-heals on deploy — no data backfill needed.

Mirrors the drop/recreate idiom in `.claude/rules/ingestion.md` § Adding a provider:
the value-list CHECK hardcodes the closed set (migrations are frozen-in-time — never
import the live `IngestionRun` trigger set). Reversible.

(The revision id keeps `alembic_version.version_num`'s VARCHAR(32) budget — the
fuller `..._runs_trigger` name overflowed by one char.)
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0025_widen_ingestion_trigger"
down_revision: str | None = "0024_skill_compat_all_agents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("chk_ingestion_runs_trigger", "ingestion_runs", type_="check")
    op.create_check_constraint(
        "chk_ingestion_runs_trigger",
        "ingestion_runs",
        "trigger IN ('scheduled','manual','force','reconcile')",
    )


def downgrade() -> None:
    op.drop_constraint("chk_ingestion_runs_trigger", "ingestion_runs", type_="check")
    op.create_check_constraint(
        "chk_ingestion_runs_trigger",
        "ingestion_runs",
        "trigger IN ('scheduled','manual','force')",
    )
