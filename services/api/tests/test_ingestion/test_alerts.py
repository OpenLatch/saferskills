"""alert_evaluator tiers (D-04-21) — warn @5%/1h, page @25%/1h."""

from __future__ import annotations

import types

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.framework.alerts import cadence_seconds, evaluate_alerts


async def _event(session: AsyncSession, *, source: str, http_status: int) -> None:
    await session.execute(
        text("""
            INSERT INTO ingestion_events
                (source, source_id, http_status, body_sha256, fetched_at,
                 duration_ms, from_cache, fetch_tier, payload)
            VALUES (:source, :sid, :status, :sha, now(), 5, false, 1, CAST('{}' AS jsonb))
        """),
        {"source": source, "sid": "x", "status": http_status, "sha": "0" * 64},
    )


def test_cadence_seconds() -> None:
    assert cadence_seconds(None) is None
    assert cadence_seconds("0 * * * *") == 3600.0  # hourly
    assert cadence_seconds("0 0 * * *") == 86400.0  # daily


@pytest.mark.asyncio
async def test_high_failure_rate_warns_and_pages(db_session: AsyncSession) -> None:
    # npm: 3 failures, 1 success → fr_1h = 0.75 (> warn 5% and > page 25%).
    for _ in range(3):
        await _event(db_session, source="npm", http_status=500)
    await _event(db_session, source="npm", http_status=200)
    await db_session.commit()

    settings = types.SimpleNamespace(slack_alerts_webhook_url=None)
    result = await evaluate_alerts(db_session, settings)
    assert result["alerts_warn"] >= 1
    assert result["alerts_page"] >= 1


@pytest.mark.asyncio
async def test_healthy_source_no_alert(db_session: AsyncSession) -> None:
    for _ in range(5):
        await _event(db_session, source="pypi", http_status=200)
    await db_session.commit()
    settings = types.SimpleNamespace(slack_alerts_webhook_url=None)
    result = await evaluate_alerts(db_session, settings)
    # pypi is all-200 → contributes nothing; other sources have no events → 0/0 → no alert.
    assert result["alerts_warn"] == 0
    assert result["alerts_page"] == 0
