"""Unit tests for the Cloudflare Turnstile verification gate.

The httpx `siteverify` round-trip is mocked — no network is touched. Pins the
three-way contract: configured-and-valid → True; configured-and-bad/outage →
False (fail-closed); unconfigured → True (dev bypass).
"""

from __future__ import annotations

import httpx
import pytest

from app.core.config import get_settings
from app.services import turnstile


class _FakeResp:
    def __init__(self, status_code: int, json_data: object) -> None:
        self.status_code = status_code
        self._json = json_data

    def json(self) -> object:
        return self._json


class _FakeClient:
    def __init__(self, *, resp: _FakeResp | None = None, exc: Exception | None = None) -> None:
        self._resp = resp
        self._exc = exc

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *_a: object) -> bool:
        return False

    async def post(self, _url: str, data: object = None) -> _FakeResp:
        if self._exc is not None:
            raise self._exc
        assert self._resp is not None
        return self._resp


def _patch_client(monkeypatch: pytest.MonkeyPatch, client: _FakeClient) -> None:
    def _factory(*_a: object, **_k: object) -> _FakeClient:
        return client

    monkeypatch.setattr(turnstile.httpx, "AsyncClient", _factory)


@pytest.fixture
def _with_secret(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    monkeypatch.setattr(get_settings(), "turnstile_secret_key", "1x000...AA")


@pytest.mark.asyncio
async def test_bypass_when_no_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unconfigured → always True (dev/test bypass; prod is guarded by config)."""
    monkeypatch.setattr(get_settings(), "turnstile_secret_key", None)
    assert await turnstile.verify_turnstile(None) is True
    assert await turnstile.verify_turnstile("anything") is True


@pytest.mark.asyncio
@pytest.mark.usefixtures("_with_secret")
async def test_missing_token_fails_when_secret_set() -> None:
    assert await turnstile.verify_turnstile(None) is False
    assert await turnstile.verify_turnstile("") is False


@pytest.mark.asyncio
@pytest.mark.usefixtures("_with_secret")
async def test_valid_token_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, _FakeClient(resp=_FakeResp(200, {"success": True})))
    assert await turnstile.verify_turnstile("good-token") is True


@pytest.mark.asyncio
@pytest.mark.usefixtures("_with_secret")
async def test_rejected_token_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(
        monkeypatch,
        _FakeClient(
            resp=_FakeResp(200, {"success": False, "error-codes": ["invalid-input-response"]})
        ),
    )
    assert await turnstile.verify_turnstile("bad-token") is False


@pytest.mark.asyncio
@pytest.mark.usefixtures("_with_secret")
async def test_siteverify_outage_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Cloudflare timeout/error must NOT silently open the gate (fail-closed)."""
    _patch_client(monkeypatch, _FakeClient(exc=httpx.ConnectTimeout("boom")))
    assert await turnstile.verify_turnstile("any-token") is False


@pytest.mark.asyncio
@pytest.mark.usefixtures("_with_secret")
async def test_non_200_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, _FakeClient(resp=_FakeResp(500, {})))
    assert await turnstile.verify_turnstile("any-token") is False
