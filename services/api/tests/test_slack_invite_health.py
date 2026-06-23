"""Tests for the Slack-invite health probe (`app/services/slack_invite_health.py`).

DB-free: exercises the probe + alert seam (`probe_and_alert`) with a mocked httpx
response and a recorded `_post_slack`, mirroring the plan's verification contract.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services import slack_invite_health

_INVITE = "https://join.slack.com/t/openlatch-community/shared_invite/zt-abc123"
_WEBHOOK = "https://hooks.slack.com/services/T000/B000/xxxx"


class _FakeResp:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


class _FakeClient:
    def __init__(self, resp: _FakeResp) -> None:
        self._resp = resp

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *_args: object) -> bool:
        return False

    async def get(self, _url: str) -> _FakeResp:
        return self._resp


def _patch_httpx(monkeypatch: pytest.MonkeyPatch, resp: _FakeResp) -> None:
    def _make_client(*_a: object, **_k: object) -> _FakeClient:
        return _FakeClient(resp)

    monkeypatch.setattr(slack_invite_health.httpx, "AsyncClient", _make_client)


def _record_post_slack(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    async def _fake(url: str, message: str) -> None:
        calls.append((url, message))

    monkeypatch.setattr(slack_invite_health, "post_slack", _fake)
    return calls


@pytest.mark.asyncio
async def test_broken_invite_fires_slack_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    # Slack serves the dead-link page with a 200 + a "no longer active" body.
    _patch_httpx(monkeypatch, _FakeResp(200, "This link is no longer active"))
    calls = _record_post_slack(monkeypatch)
    settings = Settings(slack_invite_url=_INVITE, slack_alerts_webhook_url=_WEBHOOK)

    alive = await slack_invite_health.probe_and_alert(settings)

    assert alive is False
    assert len(calls) == 1
    assert calls[0][0] == _WEBHOOK
    # Platform label: both envs page the same channel, so the message is
    # prefixed with settings.env (default "development" here).
    assert calls[0][1].startswith("[development] ")


@pytest.mark.asyncio
async def test_gone_status_is_broken(monkeypatch: pytest.MonkeyPatch) -> None:
    # 404 / 410 = the token is definitively gone → broken + alert.
    _patch_httpx(monkeypatch, _FakeResp(404, "Not Found"))
    calls = _record_post_slack(monkeypatch)
    settings = Settings(slack_invite_url=_INVITE, slack_alerts_webhook_url=_WEBHOOK)

    alive = await slack_invite_health.probe_and_alert(settings)

    assert alive is False
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_bot_gate_403_is_not_broken(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression: a VALID Slack invite 302s to the workspace join URL, which
    # returns 403 to a cookie-less/JS-less server-side client (even with a
    # browser UA) — Slack's normal login chrome, no dead-invite marker. The old
    # `status_code >= 400` rule paged on this every tick (the false positive).
    # A 403 with no marker must be treated as alive — no alert.
    _patch_httpx(monkeypatch, _FakeResp(403, "<html>… Sign in … slack-edge …</html>"))
    calls = _record_post_slack(monkeypatch)
    settings = Settings(slack_invite_url=_INVITE, slack_alerts_webhook_url=_WEBHOOK)

    alive = await slack_invite_health.probe_and_alert(settings)

    assert alive is True
    assert calls == []


@pytest.mark.asyncio
async def test_live_invite_does_not_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_httpx(monkeypatch, _FakeResp(200, "<html>Join the openlatch-community workspace</html>"))
    calls = _record_post_slack(monkeypatch)
    settings = Settings(slack_invite_url=_INVITE, slack_alerts_webhook_url=_WEBHOOK)

    alive = await slack_invite_health.probe_and_alert(settings)

    assert alive is True
    assert calls == []


@pytest.mark.asyncio
async def test_no_url_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record_post_slack(monkeypatch)
    settings = Settings(slack_invite_url=None, slack_alerts_webhook_url=_WEBHOOK)

    result = await slack_invite_health.probe_and_alert(settings)

    assert result is None
    assert calls == []


@pytest.mark.asyncio
async def test_broken_without_webhook_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    # No alert channel configured → still returns False, never raises.
    _patch_httpx(monkeypatch, _FakeResp(200, "this link is no longer active"))
    calls = _record_post_slack(monkeypatch)
    settings = Settings(slack_invite_url=_INVITE, slack_alerts_webhook_url=None)

    alive = await slack_invite_health.probe_and_alert(settings)

    assert alive is False
    assert calls == []
