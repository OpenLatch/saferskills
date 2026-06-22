"""author_summary_refresh — nightly 04:30 UTC.

Refreshes the `author_summary` materialized view (created in migration 0010) that
the Supply-Chain detector + the item-detail "author has N other items, M
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
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.config import get_settings
    from app.db.session import async_engine

    # REFRESH ... CONCURRENTLY must run outside a transaction block AND can exceed
    # the shared engine's global statement_timeout (db/session.py connect_args) on
    # a large catalog. Run it on a dedicated, short-lived AUTOCOMMIT engine with NO
    # statement_timeout so the maintenance op is never aborted mid-refresh — and so
    # the shared pool is never left with a `SET statement_timeout = 0` connection.
    # Disposed immediately after (once-nightly, so the extra connect is cheap).
    refresh_engine = create_async_engine(get_settings().database_url, isolation_level="AUTOCOMMIT")
    try:
        async with refresh_engine.connect() as conn:
            await conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY author_summary"))
    finally:
        await refresh_engine.dispose()

    async with async_engine.connect() as conn:
        count = (await conn.execute(text("SELECT count(*) FROM author_summary"))).scalar() or 0

    logger.info("author_summary_refresh.done", author_count=int(count))
    return {"author_count": int(count)}
