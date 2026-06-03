"""archive_check — daily 03:00 UTC (D-04-17).

Walks PUBLIC GITHUB capability rows with a non-zero consecutive_404_count and
flips `availability` per the timeline:

  3-6 consecutive 404s   → unavailable (yellow banner)
  7+ consecutive 404s    → archived    (gray banner) + archived=true
  back to 0 (a 200)      → recovered to available (only from 'unavailable')

The counter itself is advanced inside each adapter's MergeEngine call (a repo-level
404 fans across every capability row sharing the github_url); this task only reads
the counter and flips the state. Existing scans are always preserved. Maintainer-
archived / yanked items are flipped to 'archived' at ingest by the merger, not here.

`run_archive_check` is the testable session-taking entry point.
"""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion import procrastinate_app

logger = structlog.get_logger(__name__)


async def run_archive_check(session: AsyncSession) -> dict[str, int]:
    from app.observability.events import emit_ingestion_cycle_archived

    # Each UPDATE wrapped in a CTE that counts affected rows — `scalar_one()` is
    # typed (vs CursorResult.rowcount) and we never ship the updated ids back.
    archived = (
        await session.execute(
            text("""
            WITH u AS (
                UPDATE catalog_items
                SET availability = 'archived', archived = true, updated_at = now()
                WHERE consecutive404_count >= 7
                  AND availability <> 'archived'
                  AND source_kind = 'github' AND visibility = 'public'
                RETURNING 1
            )
            SELECT count(*) FROM u
        """)
        )
    ).scalar_one()

    unavailable = (
        await session.execute(
            text("""
            WITH u AS (
                UPDATE catalog_items
                SET availability = 'unavailable', updated_at = now()
                WHERE consecutive404_count >= 3 AND consecutive404_count < 7
                  AND availability NOT IN ('unavailable', 'archived')
                  AND source_kind = 'github' AND visibility = 'public'
                RETURNING 1
            )
            SELECT count(*) FROM u
        """)
        )
    ).scalar_one()

    recovered = (
        await session.execute(
            text("""
            WITH u AS (
                UPDATE catalog_items
                SET availability = 'available', updated_at = now()
                WHERE consecutive404_count = 0
                  AND availability = 'unavailable'
                  AND archived = false
                  AND source_kind = 'github' AND visibility = 'public'
                RETURNING 1
            )
            SELECT count(*) FROM u
        """)
        )
    ).scalar_one()
    await session.commit()

    for _ in range(archived):
        emit_ingestion_cycle_archived(source="archive_check", reason="404_timeline")

    logger.info(
        "archive_check.done", archived=archived, unavailable=unavailable, recovered=recovered
    )
    return {"archived": archived, "unavailable": unavailable, "recovered": recovered}


@procrastinate_app.periodic(cron="0 3 * * *")
@procrastinate_app.task(name="archive_check", queue="periodic", queueing_lock="archive_check_lock")
async def archive_check(timestamp: int) -> dict[str, int]:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return await run_archive_check(session)
