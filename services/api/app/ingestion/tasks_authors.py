"""author_summary_refresh — nightly 04:30 UTC (D-04-33).

Refreshes the `author_summary` materialized view (created in migration 0010) that
the I-02 Supply-Chain detector + the item-detail "author has N other items, M
Red" row read. CONCURRENTLY (the view has a unique index on github_username) so
reads aren't blocked — which means it CANNOT run inside a transaction, so we use
an AUTOCOMMIT connection rather than an AsyncSession.
"""

from __future__ import annotations

import structlog
from sqlalchemy import text

from app.ingestion import PERIODIC_MAINTENANCE_PRIORITY, procrastinate_app

logger = structlog.get_logger(__name__)


@procrastinate_app.periodic(cron="30 4 * * *")
@procrastinate_app.task(
    name="author_summary_refresh",
    queue="periodic",
    queueing_lock="author_summary_refresh_lock",
    priority=PERIODIC_MAINTENANCE_PRIORITY,
)
async def author_summary_refresh(timestamp: int) -> dict[str, int]:
    from app.db.session import async_engine

    # REFRESH ... CONCURRENTLY must run outside a transaction block.
    async with async_engine.connect() as conn:
        autocommit = await conn.execution_options(isolation_level="AUTOCOMMIT")
        await autocommit.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY author_summary"))

    async with async_engine.connect() as conn:
        count = (await conn.execute(text("SELECT count(*) FROM author_summary"))).scalar() or 0

    logger.info("author_summary_refresh.done", author_count=int(count))
    return {"author_count": int(count)}
