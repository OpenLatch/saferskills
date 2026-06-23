"""Per-adapter health alert tiers.

`alert_evaluator` runs every 15 minutes in the in-process Procrastinate worker.
For each of the 14 YAML-declared sources it reads the `ingestion_events` outbox +
`crawler_cursors.last_successful_cycle_at` and applies two independent tiers:

  Warn  — failure_rate > 5% over rolling 1h → Sentry breadcrumb + PostHog
          `ingestion_cycle_failed` (low-noise, dashboard signal).
  Page  — failure_rate > 25% / 1h  OR  > 10% sustained / 24h  OR  no successful
          cycle in 2x the source's declared cadence → Slack webhook.

Cadence is read from each source's YAML `cadence_cron` (croniter derives the
interval). Webhook-driven sources (cadence_cron = null) get no idle-alert.
A failure is any ingestion_events row whose http_status is not 200/304/0
(0 = a client-side fetch that never reached the server; not a server failure).

The page message is prefixed with `settings.env` (`[staging]` / `[production]`)
since both environments post to the same `#saferskills-alerts` channel, and the
Slack POST is throttled by a durable **per-source cooldown** (`crawler_cursors.
last_alerted_at` + `.alert_signature`, migration 0026): a sustained condition
pages once per `ingestion_alert_cooldown_s` window, then re-pages only after the
window elapses or when the failure *signature* changes. Recovery re-arms the
cooldown (clears the columns) so the next incident pages immediately. The
`alerts_page` counter still counts conditions met — only the POST is gated.

`evaluate_alerts` is the testable session-taking entry point.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import httpx
import structlog
from croniter import croniter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.ingestion import PERIODIC_MAINTENANCE_PRIORITY, procrastinate_app
from app.ingestion.config.loader import load_source_configs

logger = structlog.get_logger(__name__)

# Failure-rate thresholds. Public because `framework/health.py` (the eagle-eye
# /sources view) shares them — the dashboard and this 15-min pager MUST agree on
# what "failing" means.
WARN_1H = 0.05
PAGE_1H = 0.25
PAGE_24H = 0.10

# One query per source: 1h + 24h failure/total counts (via FILTER over a single
# 24h scan) + the cursor's last-success timestamp and the cooldown state (scalar
# subqueries). An aggregate with no GROUP BY always returns exactly one row, even
# with zero events.
_HEALTH = text("""
    SELECT
        count(*) FILTER (
            WHERE fetched_at > now() - interval '1 hour'
              AND http_status NOT IN (200, 304, 0)
        ) AS fail_1h,
        count(*) FILTER (WHERE fetched_at > now() - interval '1 hour') AS total_1h,
        count(*) FILTER (WHERE http_status NOT IN (200, 304, 0))       AS fail_24h,
        count(*)                                                       AS total_24h,
        (SELECT last_successful_cycle_at FROM crawler_cursors WHERE source = :source)
            AS last_success,
        (SELECT last_alerted_at FROM crawler_cursors WHERE source = :source)
            AS last_alerted,
        (SELECT alert_signature FROM crawler_cursors WHERE source = :source)
            AS alert_signature
    FROM ingestion_events
    WHERE source = :source AND fetched_at > now() - interval '24 hours'
""")

# Cooldown bookkeeping on the per-source crawler_cursors row. `now()` (the
# server-side transaction clock) stamps the page; recovery clears both columns.
_MARK_ALERTED = text("""
    UPDATE crawler_cursors
    SET last_alerted_at = now(), alert_signature = :sig
    WHERE source = :source
""")
_CLEAR_ALERTED = text("""
    UPDATE crawler_cursors
    SET last_alerted_at = NULL, alert_signature = NULL
    WHERE source = :source
""")


def cadence_seconds(cadence_cron: str | None) -> float | None:
    """Interval between two consecutive cron fires, or None for webhook sources.

    Public — shared with `framework/health.py`.
    """
    if not cadence_cron:
        return None
    try:
        base = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
        itr = croniter(cadence_cron, base)
        first = itr.get_next(dt.datetime)
        second = itr.get_next(dt.datetime)
        return (second - first).total_seconds()
    except ValueError, KeyError:
        return None


async def post_slack(webhook_url: str, message: str) -> None:
    """POST a plain-text message to a Slack incoming-webhook.

    Public — shared with `app/services/slack_invite_health.py` (the invite
    health probe pages the same channel on a broken invite)."""
    async with httpx.AsyncClient(timeout=15) as client:
        await client.post(webhook_url, json={"text": message})


def _breadcrumb(source: str, fr_1h: float) -> None:
    try:
        import sentry_sdk

        sentry_sdk.add_breadcrumb(category="ingestion", message=f"warn: {source} fr_1h={fr_1h:.2%}")
    except Exception:
        logger.debug("alert_evaluator.sentry_breadcrumb_skipped", source=source)


async def evaluate_alerts(session: AsyncSession, settings: Any) -> dict[str, int]:
    """Per-source warn/page evaluation. Testable session-taking entry point."""
    from app.observability.events import emit_ingestion_cycle_failed

    now = dt.datetime.now(tz=dt.UTC)
    alerts_warn = 0
    alerts_page = 0
    cooldown_dirty = False
    for source, cfg in load_source_configs().items():
        row = (await session.execute(_HEALTH, {"source": source})).one()
        last_success = row.last_success

        fr_1h = row.fail_1h / row.total_1h if row.total_1h else 0.0
        fr_24h = row.fail_24h / row.total_24h if row.total_24h else 0.0

        cadence_s = cadence_seconds(cfg.cadence_cron)
        silent_too_long = False
        if cadence_s is not None and last_success is not None:
            age = (now - last_success).total_seconds()
            silent_too_long = age > (cadence_s * 2)

        if fr_1h > WARN_1H:
            alerts_warn += 1
            _breadcrumb(source, fr_1h)
            emit_ingestion_cycle_failed(source=source, reason="other")

        page_now = fr_1h > PAGE_1H or fr_24h > PAGE_24H or silent_too_long
        if page_now:
            alerts_page += 1

        # The Slack POST + its cooldown bookkeeping live entirely inside the
        # webhook-configured branch (so a None webhook is a clean no-op and never
        # touches crawler_cursors). The dashboard `alerts_page` count above is
        # unchanged — only the POST is gated.
        if settings.slack_alerts_webhook_url:
            if page_now:
                signature = "|".join(
                    name
                    for cond, name in (
                        (silent_too_long, "silent"),
                        (fr_1h > PAGE_1H, "fr_1h"),
                        (fr_24h > PAGE_24H, "fr_24h"),
                    )
                    if cond
                )
                cooldown_s = settings.ingestion_alert_cooldown_s
                suppressed = (
                    cooldown_s > 0
                    and row.last_alerted is not None
                    and row.alert_signature == signature
                    and (now - row.last_alerted).total_seconds() < cooldown_s
                )
                if not suppressed:
                    msg = f"[{settings.env}] :rotating_light: *Ingestion alert* — `{source}` "
                    if silent_too_long and cadence_s is not None:
                        msg += f"no successful cycle in {int(cadence_s * 2) // 3600}h "
                    msg += f"(fr_1h={fr_1h:.0%}, fr_24h={fr_24h:.0%})"
                    try:
                        await post_slack(settings.slack_alerts_webhook_url, msg)
                    except Exception:
                        # Failed post → don't mark; the next tick retries.
                        logger.warning("alert_evaluator.slack_post_failed", source=source)
                    else:
                        await session.execute(_MARK_ALERTED, {"sig": signature, "source": source})
                        cooldown_dirty = True
            elif row.last_alerted is not None:
                # Recovery: re-arm so the next incident pages immediately. Clearing
                # is not itself a notification (no "resolved" note by decision).
                await session.execute(_CLEAR_ALERTED, {"source": source})
                cooldown_dirty = True

    if cooldown_dirty:
        await session.commit()

    logger.info("alert_evaluator.done", warn=alerts_warn, page=alerts_page)
    return {"alerts_warn": alerts_warn, "alerts_page": alerts_page}


@procrastinate_app.periodic(cron="*/15 * * * *")
@procrastinate_app.task(
    name="alert_evaluator",
    queue="periodic",
    queueing_lock="alert_evaluator_lock",
    priority=PERIODIC_MAINTENANCE_PRIORITY,
)
async def alert_evaluator(timestamp: int) -> dict[str, int]:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        return await evaluate_alerts(session, get_settings())
