"""WS2 — transient-retry wrapper behaviour (`shared/http_client.request_with_retries`).

Proves the chosen contract: transient blips (502/503/504 + connect/read timeouts)
are retried and absorbed, but a SUSTAINED degradation still surfaces to the caller
(returned 503 / re-raised exception) so the e2e gate stays honest.

Sync tests over `asyncio.run` (the e2e package ships no pytest-asyncio); a tiny
`backoff` keeps the exponential sleeps negligible. A scripted fake stands in for
`httpx.AsyncClient.request` so no network is touched.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, cast

import httpx
import pytest

from saferskills_e2e.shared.http_client import request_with_retries

# Negligible backoff so the retry sleeps don't slow the test (1ms, 2ms, ...).
_FAST_BACKOFF = 0.001


class _ScriptedClient:
    """Minimal stand-in for `httpx.AsyncClient` — yields scripted outcomes in order.

    Each outcome is either an `httpx.Response` (returned) or an `Exception`
    (raised). `calls` records how many times `request` was invoked.
    """

    def __init__(self, outcomes: list[httpx.Response | Exception]) -> None:
        self._outcomes = outcomes
        self.calls = 0

    async def request(self, _method: str, _url: str, **_kwargs: Any) -> httpx.Response:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _client(outcomes: list[httpx.Response | Exception]) -> _ScriptedClient:
    return _ScriptedClient(outcomes)


def _run(coro: Coroutine[Any, Any, httpx.Response]) -> httpx.Response:
    return asyncio.run(coro)


def _call(client: _ScriptedClient, retries: int = 3) -> Coroutine[Any, Any, httpx.Response]:
    return request_with_retries(
        cast(httpx.AsyncClient, client),
        "GET",
        "http://test/api/v1/items",
        retries=retries,
        backoff=_FAST_BACKOFF,
    )


def test_retries_transient_503_then_succeeds() -> None:
    client = _client([httpx.Response(503), httpx.Response(503), httpx.Response(200)])
    resp = _run(_call(client))
    assert resp.status_code == 200
    assert client.calls == 3  # two transient 503s retried, third succeeds


def test_sustained_503_returns_the_503() -> None:
    # The contract: a SUSTAINED 503 is NOT masked — it is returned so the caller
    # (raise_for_status / status check) fails the command and blocks the deploy.
    client = _client([httpx.Response(503), httpx.Response(503), httpx.Response(503)])
    resp = _run(_call(client))
    assert resp.status_code == 503
    assert client.calls == 3


def test_read_timeout_then_succeeds() -> None:
    client = _client([httpx.ReadTimeout("slow"), httpx.Response(200)])
    resp = _run(_call(client))
    assert resp.status_code == 200
    assert client.calls == 2


def test_sustained_connect_error_reraises() -> None:
    client = _client(
        [httpx.ConnectError("boom"), httpx.ConnectError("boom"), httpx.ConnectError("boom")]
    )
    with pytest.raises(httpx.ConnectError):
        _run(_call(client))
    assert client.calls == 3


def test_4xx_passes_through_without_retry() -> None:
    client = _client([httpx.Response(404)])
    resp = _run(_call(client))
    assert resp.status_code == 404
    assert client.calls == 1  # a 4xx is a real result — never retried


def test_non_transient_500_passes_through_without_retry() -> None:
    # 500 is NOT in the transient set {502,503,504} — a real server error, no retry.
    client = _client([httpx.Response(500)])
    resp = _run(_call(client))
    assert resp.status_code == 500
    assert client.calls == 1
