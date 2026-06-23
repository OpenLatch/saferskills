"""add crawler_cursors alert-cooldown columns

Revision ID: 0026_add_crawler_alert_cooldown
Revises: 0025_widen_ingestion_trigger
Create Date: 2026-06-23

Backs the per-source ingestion-alert cooldown (`app/ingestion/framework/alerts.py`).
`alert_evaluator` is level-triggered + stateless: it re-posts the same Slack page
every 15 min for as long as a condition holds (the `#saferskills-alerts` npm-spam
incident). The cooldown makes a sustained condition page ONCE per window, then
re-page only after the window elapses or when the failure's nature changes.

Two NULLABLE columns on the existing per-source `crawler_cursors` row (durable
because the worker restarts often — an in-memory dict would reset on every restart
and the spam would resume):

  - `last_alerted_at TIMESTAMPTZ NULL` — when this source last paged Slack.
  - `alert_signature VARCHAR(100) NULL` — a stable "|"-joined fingerprint of the
    active page reasons (silent|fr_1h|fr_24h); a signature change re-pages within
    the window. Recovery (no page condition) clears both → the next incident pages
    immediately.

No CHECK / enum (the signature is free text bounded to 100 chars). Reversible —
`downgrade()` drops both columns.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_add_crawler_alert_cooldown"
down_revision: str | None = "0025_widen_ingestion_trigger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "crawler_cursors",
        sa.Column("last_alerted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "crawler_cursors",
        sa.Column("alert_signature", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("crawler_cursors", "alert_signature")
    op.drop_column("crawler_cursors", "last_alerted_at")
