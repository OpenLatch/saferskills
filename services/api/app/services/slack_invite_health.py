"""Background health probe for the community Slack shared-invite link.

There is no supported Slack API to programmatically mint a workspace shared
invite, so the `SLACK_INVITE_URL` redirect target is a Slack-native "Never
expires" link. A never-expire link can still break (workspace renamed, link
revoked, 2,000-member cap reached), so this loop GETs it on a slow cadence and,
on breakage, fires the same Slack page channel as the ingestion alerts
(`SLACK_ALERTS_WEBHOOK_URL`) plus a Sentry message. The redirect indirection
then means a maintainer fixes it with a one-value `[env]` change.

Mirrors `app/core/sweeps.py::run_sweep_loop`: an asyncio loop started from the
FastAPI lifespan AFTER migrations + the pool are up, race-safe across concurrent
Machines via a session-level `pg_try_advisory_lock` (a held lock makes the other
Machine skip the tick, not block). The httpx usage mirrors
`app/services/github_stars.py` / `turnstile.py`.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.db.session import AsyncSessionLocal
from app.ingestion.framework.alerts import post_slack

logger = logging.getLogger(__name__)

# Next free advisory key after migrations (0x5AFE5C11) / expiry sweep
# (0x5AFE5C12) / ingestion worker (0x5AFE5C13).
_HEALTH_LOCK_KEY = 0x5AFE5C14
_TIMEOUT_SECONDS = 10.0

# Lowercased substrings Slack renders on a dead/expired shared-invite page.
# (No "this link is no longer active" — the shorter "no longer active" already
# matches it.)
_BROKEN_MARKERS = (
    "no longer active",
    "isn't active",
    "couldn't find",
)


async def _probe_invite(url: str) -> bool:
    """GET the invite; return ``True`` if live, ``False`` only if *positively* broken.

    Slack **bot-gates** server-side requests: a VALID invite 302-redirects to
    ``<workspace>.slack.com/join/shared_invite/…`` which then returns **403** to
    any cookie-less / JS-less client — confirmed it 403s even with a browser
    User-Agent (the body is Slack's normal login chrome, not a dead-invite page).
    So a 4xx — 403 in particular — is NOT a dead-invite signal; the old
    ``status_code >= 400`` rule pages on *every healthy invite* (the false
    positive this fixes).

    An invite is called broken only on a **positive** dead signal:
      - status ``404`` / ``410`` — the token is definitively gone; or
      - a dead-invite copy marker in the body (Slack serves the "no longer
        active" page with a 200 on `join.slack.com`).

    A 403 / 401 / JS-gated response with no marker is treated as **alive**
    (inconclusive — never page on it). This trades a rare false-negative (a dead
    invite Slack also 403s, with no marker) for eliminating the false-positive
    storm; for a pager, that bias is the right one.
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, follow_redirects=True) as client:
        resp = await client.get(url)
    if resp.status_code in (404, 410):
        return False
    body = resp.text.lower()
    return not any(marker in body for marker in _BROKEN_MARKERS)


async def _alert_broken(settings: Settings, detail: str) -> None:
    """Fire the Slack page channel + a Sentry message for a broken invite.

    Both sinks are best-effort and independently guarded — one failing must
    never propagate out of the probe (which would kill the loop)."""
    message = (
        ":warning: *SaferSkills Slack invite is broken* — the `SLACK_INVITE_URL` "
        f"redirect target appears dead: {detail}. Rotate it via the API `[env]`."
    )
    if settings.slack_alerts_webhook_url:
        try:
            await post_slack(settings.slack_alerts_webhook_url, message)
        except Exception:
            logger.warning("slack invite health: slack alert post failed")
    try:
        import sentry_sdk

        sentry_sdk.capture_message(f"slack invite broken: {detail}", level="error")
    except Exception:
        logger.debug("slack invite health: sentry capture skipped")


async def probe_and_alert(settings: Settings) -> bool | None:
    """Probe the configured invite; alert on breakage. No DB. Returns liveness.

    The testable seam: returns ``None`` when no invite URL is configured,
    ``True`` when live, ``False`` (after alerting) when broken."""
    url = settings.slack_invite_url
    if not url:
        return None
    alive = await _probe_invite(url)
    if not alive:
        await _alert_broken(settings, url)
    return alive


async def _run_one_tick() -> None:
    """One probe tick under the advisory lock (dedup across Machines)."""
    settings = get_settings()
    if not settings.slack_invite_url:
        return
    async with AsyncSessionLocal() as session:
        got = (
            await session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _HEALTH_LOCK_KEY})
        ).scalar_one()
        if not got:
            return
        try:
            await probe_and_alert(settings)
        finally:
            await session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _HEALTH_LOCK_KEY})
            await session.commit()


async def run_slack_invite_health_loop() -> None:
    """Every `slack_invite_health_interval_seconds`, probe the invite once.

    One bad tick logs a WARN and never kills the loop (like `_run_one_sweep`).
    Cancellation-safe."""
    interval = get_settings().slack_invite_health_interval_seconds
    logger.info("slack invite health loop started (interval=%ss)", interval)
    try:
        while True:
            try:
                await _run_one_tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "slack invite health tick failed; continuing (%s)", type(exc).__name__
                )
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("slack invite health loop cancelled")
        raise
