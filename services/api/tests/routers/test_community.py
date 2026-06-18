"""Tests for GET /api/v1/community/slack/redirect + the invite-URL validator."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import app

_INVITE = "https://join.slack.com/t/openlatch-community/shared_invite/zt-abc123"


@pytest.mark.asyncio
async def test_redirect_302_to_configured_invite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.routers.community.get_settings",
        lambda: SimpleNamespace(slack_invite_url=_INVITE),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/community/slack/redirect")

    assert resp.status_code == 302
    assert resp.headers["location"] == _INVITE


@pytest.mark.asyncio
async def test_redirect_503_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.routers.community.get_settings",
        lambda: SimpleNamespace(slack_invite_url=None),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/community/slack/redirect")

    assert resp.status_code == 503


def test_validator_rejects_non_slack_host() -> None:
    with pytest.raises(ValidationError):
        Settings(slack_invite_url="https://evil.com")


def test_validator_rejects_http_scheme() -> None:
    with pytest.raises(ValidationError):
        Settings(slack_invite_url="http://join.slack.com/t/x/shared_invite/zt-1")


def test_validator_accepts_join_slack_com() -> None:
    settings = Settings(slack_invite_url=_INVITE)
    assert settings.slack_invite_url == _INVITE


def test_validator_normalizes_blank_to_none() -> None:
    # The .env.example / docker-compose `${SLACK_INVITE_URL:-}` empty default must
    # boot, not crash on urlsplit(""): blank → unset.
    assert Settings(slack_invite_url="").slack_invite_url is None
    assert Settings(slack_invite_url="   ").slack_invite_url is None
