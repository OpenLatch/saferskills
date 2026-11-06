"""recompute latest_scan_* for items whose latest scans share a timestamp

Revision ID: 0028_latest_scan_tie_break
Revises: 0027_catalog_latest_scan_columns
Create Date: 2026-11-06

One scan run could write two scans for the same catalog item (a plugin anchored at
both its root and its `.claude-plugin` folder, or two names with the same slug), so
both carry the same `scanned_at`. `latest_scan_*` broke that tie on id, which could
show a green score over a red one. The tie now goes to the lower score
(`app.queries.NEWEST_SCAN_FIRST`); this recomputes only the items with a tie, a few
thousand rows, so it is quick enough to run at boot.

Data only. `downgrade()` is a no-op: the previous pick was arbitrary, not a state worth
restoring.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_latest_scan_tie_break"
down_revision: str | None = "0027_catalog_latest_scan_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copy of the tie-break at the time of writing; never import live app code here.
RETIE_SQL = sa.text("""
    WITH tied AS (
        SELECT c.id
        FROM catalog_items c
        JOIN scans s ON s.catalog_item_id = c.id AND s.scanned_at = c.latest_scanned_at
        WHERE s.tier <> 'unscoped'
        GROUP BY c.id
        HAVING count(*) > 1
    ), latest AS (
        SELECT t.id AS item_id, s.id, s.aggregate_score, s.tier, s.scanned_at
        FROM tied t
        CROSS JOIN LATERAL (
            SELECT id, aggregate_score, tier, scanned_at
            FROM scans
            WHERE catalog_item_id = t.id AND tier <> 'unscoped'
            ORDER BY scanned_at DESC, aggregate_score ASC, id DESC
            LIMIT 1
        ) s
    )
    UPDATE catalog_items c
    SET latest_scan_id = l.id,
        latest_scan_score = l.aggregate_score,
        latest_scan_tier = l.tier,
        latest_scanned_at = l.scanned_at
    FROM latest l
    WHERE c.id = l.item_id AND c.latest_scan_id IS DISTINCT FROM l.id
""")


def upgrade() -> None:
    op.execute(RETIE_SQL)


def downgrade() -> None:
    pass
