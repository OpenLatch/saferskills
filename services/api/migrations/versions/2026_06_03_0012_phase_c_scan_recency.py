"""Phase C scan-recency columns on catalog_items

Revision ID: 0012_phase_c_scan_recency
Revises: 0011_ingestion_outbox_tables
Create Date: 2026-06-03

I-04 Phase C. Adds the two scan-depth recency columns the auto-scan triggers read
(D-04-14 / D-04-15): `last_deep_scan_at` + `last_lite_scan_at`. These were
intentionally deferred from migration 0010 (no Phase-A consumer); Phase C is the
consumer. They mirror the generated catalog_item model (schema-driven — the wire
fields `lastDeepScanAt` / `lastLiteScanAt` were added to catalog-item.schema.json).

`scans.tier` is the trust badge (green/yellow/orange/red/unscoped), NOT a scan
depth — these columns are the depth-recency source enqueue_scan stamps on
completion. No scan_runs.scan_depth column is added: enqueue_scan's completion
wrapper knows the depth and stamps the right column directly (lean approach).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_phase_c_scan_recency"
down_revision: str | None = "0011_ingestion_outbox_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "catalog_items",
        sa.Column("last_deep_scan_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "catalog_items",
        sa.Column("last_lite_scan_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial indexes: the auto-scan triggers select rows that are NULL or stale,
    # ordered by popularity_score — these support the recency predicate scan.
    op.create_index(
        "idx_catalog_items_last_deep_scan_at",
        "catalog_items",
        ["last_deep_scan_at"],
    )
    op.create_index(
        "idx_catalog_items_last_lite_scan_at",
        "catalog_items",
        ["last_lite_scan_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_catalog_items_last_lite_scan_at", table_name="catalog_items")
    op.drop_index("idx_catalog_items_last_deep_scan_at", table_name="catalog_items")
    op.drop_column("catalog_items", "last_lite_scan_at")
    op.drop_column("catalog_items", "last_deep_scan_at")
