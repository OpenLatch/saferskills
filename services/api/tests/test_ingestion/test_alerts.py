"""alert_evaluator tiers — warn @5%/1h, page @25%/1h."""

from __future__ import annotations

import types

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.framework import alerts as alerts_mod
from app.ingestion.framework.alerts import cadence_seconds, evaluate_alerts

_WEBHOOK = "https://hooks.slack.com/services/T000/B000/xxxx"


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


def _settings(
    *, env: str = "staging", cooldown_s: float = 14_400.0, webhook: str | None = _WEBHOOK
) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        slack_alerts_webhook_url=webhook,
        env=env,
        ingestion_alert_cooldown_s=cooldown_s,
    )


def _record_post_slack(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    async def _fake(url: str, message: str) -> None:
        calls.append((url, message))

    monkeypatch.setattr(alerts_mod, "post_slack", _fake)
    return calls


async def _npm_failing(session: AsyncSession) -> None:
    """npm with fr_1h = 0.75 → page signature 'fr_1h|fr_24h'."""
    for _ in range(3):
        await _event(session, source="npm", http_status=500)
    await _event(session, source="npm", http_status=200)
    await session.commit()


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


@pytest.mark.asyncio
async def test_message_carries_env_prefix(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _npm_failing(db_session)
    calls = _record_post_slack(monkeypatch)

    await evaluate_alerts(db_session, _settings(env="staging"))

    assert len(calls) == 1
    assert calls[0][0] == _WEBHOOK
    assert calls[0][1].startswith("[staging] ")


@pytest.mark.asyncio
async def test_cooldown_suppresses_repeat_within_window(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # This is the assertion that fails on `main` (no cooldown) and passes here.
    await _npm_failing(db_session)
    calls = _record_post_slack(monkeypatch)
    settings = _settings(cooldown_s=14_400.0)

    await evaluate_alerts(db_session, settings)  # pages
    await evaluate_alerts(db_session, settings)  # same signature, within window → suppressed

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_cooldown_disabled_pages_every_tick(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # cooldown_s=0 restores the legacy always-page-every-tick behaviour.
    await _npm_failing(db_session)
    calls = _record_post_slack(monkeypatch)
    settings = _settings(cooldown_s=0.0)

    await evaluate_alerts(db_session, settings)
    await evaluate_alerts(db_session, settings)

    assert len(calls) == 2


@pytest.mark.asyncio
async def test_cooldown_expiry_repages(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # last_alerted older than the window (signature matching) → re-pages.
    await _npm_failing(db_session)
    await db_session.execute(
        text("""
            UPDATE crawler_cursors
            SET last_alerted_at = now() - interval '5 hours', alert_signature = :sig
            WHERE source = 'npm'
        """),
        {"sig": "fr_1h|fr_24h"},
    )
    await db_session.commit()
    calls = _record_post_slack(monkeypatch)

    await evaluate_alerts(db_session, _settings(cooldown_s=14_400.0))

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_signature_change_repages_within_window(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A fresh last_alerted (within window) but a DIFFERENT prior signature → the
    # nature of the failure changed → re-page even inside the cooldown window.
    await _npm_failing(db_session)
    await db_session.execute(
        text("""
            UPDATE crawler_cursors
            SET last_alerted_at = now(), alert_signature = 'silent'
            WHERE source = 'npm'
        """),
    )
    await db_session.commit()
    calls = _record_post_slack(monkeypatch)

    await evaluate_alerts(db_session, _settings(cooldown_s=14_400.0))

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_recovery_clears_cooldown(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # npm healthy now, but a prior page armed the cooldown → recovery clears both
    # columns (re-arm). No "resolved" notification is sent.
    for _ in range(3):
        await _event(db_session, source="npm", http_status=200)
    await db_session.execute(
        text("""
            UPDATE crawler_cursors
            SET last_alerted_at = now(), alert_signature = 'fr_1h|fr_24h'
            WHERE source = 'npm'
        """),
    )
    await db_session.commit()
    calls = _record_post_slack(monkeypatch)

    await evaluate_alerts(db_session, _settings(cooldown_s=14_400.0))

    assert calls == []
    cleared = (
        await db_session.execute(
            text("SELECT last_alerted_at, alert_signature FROM crawler_cursors WHERE source='npm'")
        )
    ).one()
    assert cleared.last_alerted_at is None
    assert cleared.alert_signature is None
