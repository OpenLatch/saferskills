"""Robustness guard tests — locks the "zero unhandled tracebacks" invariant.

The ingestion + scan pipeline robustness overhaul (WS-1..WS-8) turns every
provider/transport/shape-drift failure into a clean WARN + a recorded
skipped/failed result. This file is the acceptance bar (WS-9): it injects each
failure class and asserts NO exception propagates and the cycle/source is not
wedged. Reverting any one fix (e.g. WS-3's permanent-dead-letter, WS-5's per-item
skip) should turn one of these red.

Covers:
  - Retry taxonomy (WS-3): permanent → dead-letter now; transient → schedule.
  - Shared failure classifier (WS-4).
  - GitHub App token-mint failure → None, never a raised traceback (WS-1).
  - Malformed Content-Length doesn't raise in the response hook (WS-8a).
  - Per-item isolation: a poisoned item is skipped, the cycle completes (WS-5).
  - npm non-200 stream → success=False cursor, no silent false-green (WS-8b).
  - Cycle-level provider failure (403/429/5xx) → clean failed result, no raise.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.config.loader import SourceConfig
from app.ingestion.framework.base_adapter import NormalizedItem, RawItem
from app.ingestion.framework.registry_adapter import RegistryAdapter

# ──────────────────────────────────────────────────────────────────────────
# WS-3 — retry taxonomy
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "exc",
    [
        KeyError("missing"),
        ValueError("bad"),
        TypeError("wrong type"),
        AttributeError("no attr"),
        IndexError("oob"),
    ],
)
def test_retry_permanent_dead_letters_immediately(exc: BaseException) -> None:
    """A permanent shape-drift error must dead-letter NOW (None), never schedule a
    retry — a deterministic bug just re-fails 4x with a full refetch each (WS-3)."""
    from app.ingestion.framework.retry import IngestionRetry

    job = MagicMock()
    job.attempts = 1  # first failure — would normally schedule the 1-min retry
    assert IngestionRetry().get_retry_decision(exception=exc, job=job) is None


def test_retry_pydantic_validation_error_is_permanent() -> None:
    from pydantic import BaseModel, ValidationError

    from app.ingestion.framework.retry import IngestionRetry, is_permanent_failure

    class _M(BaseModel):
        x: int

    try:
        _M(x="not-an-int")  # type: ignore[arg-type]
        raise AssertionError("expected ValidationError")
    except ValidationError as exc:
        assert is_permanent_failure(exc) is True
        job = MagicMock()
        job.attempts = 1
        assert IngestionRetry().get_retry_decision(exception=exc, job=job) is None


@pytest.mark.parametrize("attempt", [1, 2, 3, 4])
def test_retry_transient_schedules_within_window(attempt: int) -> None:
    """A transient error schedules a retry (non-None) for each of the 4 scheduled
    attempts — the escalating 1m/5m/30m/6h window (WS-3). The exact backoff is the
    `_SCHEDULE_SECONDS` tuple; here we lock that transient ≠ dead-letter."""
    from app.ingestion.framework.retry import IngestionRetry

    job = MagicMock()
    job.attempts = attempt
    decision = IngestionRetry().get_retry_decision(exception=httpx.ConnectError("blip"), job=job)
    assert decision is not None


def test_retry_transient_exhausts_to_dead_letter() -> None:
    from app.ingestion.framework.retry import IngestionRetry

    job = MagicMock()
    job.attempts = 5  # past the 4-entry schedule
    assert (
        IngestionRetry().get_retry_decision(exception=httpx.ConnectError("blip"), job=job) is None
    )


# ──────────────────────────────────────────────────────────────────────────
# WS-4 — shared failure classifier
# ──────────────────────────────────────────────────────────────────────────


def _status_error(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://api.github.com/x")
    return httpx.HTTPStatusError("e", request=req, response=httpx.Response(code, request=req))


@pytest.mark.parametrize(
    "exc,expected",
    [
        (httpx.ReadTimeout("t"), "timeout"),
        (_status_error(403), "rate_limit"),
        (_status_error(429), "rate_limit"),
        (_status_error(500), "http_5xx"),
        (_status_error(503), "http_5xx"),
        (KeyError("k"), "permanent"),
        (ValueError("v"), "permanent"),
        (httpx.ConnectError("c"), "other"),
        (OSError("o"), "other"),
    ],
)
def test_classify_failure(exc: BaseException, expected: str) -> None:
    from app.ingestion.framework.failure import classify_failure

    assert classify_failure(exc) == expected


# ──────────────────────────────────────────────────────────────────────────
# WS-1 — GitHub App token-mint failure → None (never a raised traceback)
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_token_mint_500_returns_none_and_negative_caches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 500 from the installation-token endpoint must be swallowed → None (callers
    fall back to anonymous), and the negative cache must stop a re-attempt (WS-1)."""
    import jwt

    from app.core import github_app_token as gat

    # Reset module caches so the test is order-independent.
    gat._GITHUB_APP_TOKEN.clear()  # pyright: ignore[reportPrivateUsage]
    gat._MINT_STATE["failed_until"] = 0.0  # pyright: ignore[reportPrivateUsage]

    def _fake_encode(*a: Any, **k: Any) -> str:
        return "fake.jwt"

    monkeypatch.setattr(jwt, "encode", _fake_encode)

    post_calls = {"n": 0}

    class _FakeResp:
        status_code = 500

        def raise_for_status(self) -> None:
            req = httpx.Request("POST", "https://api.github.com/app/installations/1/access_tokens")
            raise httpx.HTTPStatusError(
                "boom", request=req, response=httpx.Response(500, request=req)
            )

        def json(self) -> dict[str, Any]:
            return {}

    class _FakeClient:
        def __init__(self, *a: Any, **k: Any) -> None: ...
        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *a: Any) -> None:
            return None

        async def post(self, *a: Any, **k: Any) -> _FakeResp:
            post_calls["n"] += 1
            return _FakeResp()

    monkeypatch.setattr(gat.httpx, "AsyncClient", _FakeClient)

    settings = MagicMock()
    settings.github_app_id = "123"
    settings.github_app_private_key = "key"
    settings.github_app_installation_id = "1"

    assert await gat.get_github_app_installation_token(settings) is None
    assert post_calls["n"] == 1
    # Negative cache — a second call within the window does NOT re-attempt the POST.
    assert await gat.get_github_app_installation_token(settings) is None
    assert post_calls["n"] == 1


@pytest.mark.asyncio
async def test_token_missing_creds_returns_none() -> None:
    from app.core import github_app_token as gat

    gat._GITHUB_APP_TOKEN.clear()  # pyright: ignore[reportPrivateUsage]
    gat._MINT_STATE["failed_until"] = 0.0  # pyright: ignore[reportPrivateUsage]
    settings = MagicMock()
    settings.github_app_id = None
    settings.github_app_private_key = None
    settings.github_app_installation_id = None
    assert await gat.get_github_app_installation_token(settings) is None


# ──────────────────────────────────────────────────────────────────────────
# WS-8a — malformed Content-Length must not raise in the response hook
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_malformed_content_length_does_not_raise() -> None:
    from app.ingestion.framework.http_client import (
        _body_size_cap_hook,  # pyright: ignore[reportPrivateUsage]
    )

    req = httpx.Request("GET", "https://api.github.com/x")
    resp = httpx.Response(200, headers={"content-length": "not-a-number"}, request=req)
    # Must NOT raise (WS-8a) — malformed header treated as unknown size.
    await _body_size_cap_hook(resp)  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_oversize_content_length_still_raises() -> None:
    from app.ingestion.framework.exceptions import BodyTooLargeError
    from app.ingestion.framework.http_client import (
        _body_size_cap_hook,  # pyright: ignore[reportPrivateUsage]
    )

    req = httpx.Request("GET", "https://api.github.com/x")
    resp = httpx.Response(200, headers={"content-length": str(50 * 1024 * 1024)}, request=req)
    with pytest.raises(BodyTooLargeError):
        await _body_size_cap_hook(resp)  # pyright: ignore[reportPrivateUsage]


# ──────────────────────────────────────────────────────────────────────────
# WS-5 — per-item isolation: a poisoned item is skipped, the cycle completes
# ──────────────────────────────────────────────────────────────────────────


def _config() -> SourceConfig:
    return SourceConfig(name="github_topics", kind="api", hosts=["api.github.com"], discovery={})


class _PoisonNormalizeAdapter(RegistryAdapter):
    """Yields a good item then one whose normalize() raises (provider shape-drift)."""

    def __init__(self, config: SourceConfig, items: list[RawItem]) -> None:
        super().__init__(config)
        self._items = items

    async def list_items(self, client: Any):
        for item in self._items:
            yield item

    def normalize(self, raw: RawItem) -> NormalizedItem | None:
        if raw.source_id == "poison/item":
            # A 200 whose body is missing a required field → KeyError in normalize.
            raise KeyError("expected 'name' key in payload")
        return NormalizedItem(
            github_org="acme",
            github_repo="good",
            display_name="good",
            metadata_files={},
            aggregator_listings=["github_topics"],
        )


def _raw(source_id: str) -> RawItem:
    return RawItem(
        source_id=source_id,
        raw_body_bytes=b"{}",
        raw_body_hash="0" * 64,
        http_status=200,
        fetch_tier=1,
        payload_hint={},
    )


def _mock_settings() -> Any:
    s = MagicMock()
    s.hishel_db_path = ":memory:"
    s.hishel_github_ttl_seconds = 3600
    s.hishel_aggregator_ttl_seconds = 3600
    return s


@pytest.mark.asyncio
async def test_poisoned_item_skipped_cycle_completes(db_session: AsyncSession) -> None:
    """A normalize() KeyError on one item is isolated: ONE skip, the good item still
    upserts, the cycle returns clean counters with NO exception propagating (WS-5)."""
    adapter = _PoisonNormalizeAdapter(_config(), [_raw("good/item"), _raw("poison/item")])

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.ingestion.framework.registry_adapter.HttpClientFactory.build",
            return_value=mock_client,
        ),
        patch("app.ingestion.framework.registry_adapter.MergeEngine") as MockMerge,
        patch("app.ingestion.framework.registry_adapter.OutboxWriter") as MockOutbox,
    ):
        mock_merger = AsyncMock()
        mock_merger.upsert = AsyncMock(return_value="added")
        MockMerge.return_value = mock_merger
        MockOutbox.return_value = AsyncMock()
        db_session.commit = AsyncMock()

        counters = await adapter.run_cycle(db_session, _mock_settings())

    assert counters["items_seen"] == 2
    assert counters["items_added"] == 1
    assert counters["items_skipped"] == 1
    # The good item upserted; the poisoned one never reached the merger.
    assert mock_merger.upsert.await_count == 1


@pytest.mark.asyncio
async def test_write_phase_error_skipped_via_savepoint(db_session: AsyncSession) -> None:
    """A shape-drift error during the DB-write phase (upsert) rolls back just that
    item's SAVEPOINT — the batch survives, the cycle completes, no raise (WS-5)."""

    class _GoodAdapter(RegistryAdapter):
        def __init__(self, config: SourceConfig, items: list[RawItem]) -> None:
            super().__init__(config)
            self._items = items

        async def list_items(self, client: Any):
            for item in self._items:
                yield item

        def normalize(self, raw: RawItem) -> NormalizedItem | None:
            return NormalizedItem(
                github_org="acme",
                github_repo=raw.source_id.split("/")[-1],
                display_name=raw.source_id,
                metadata_files={},
                aggregator_listings=["github_topics"],
            )

    adapter = _GoodAdapter(_config(), [_raw("a/one"), _raw("a/two")])

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.ingestion.framework.registry_adapter.HttpClientFactory.build",
            return_value=mock_client,
        ),
        patch("app.ingestion.framework.registry_adapter.MergeEngine") as MockMerge,
        patch("app.ingestion.framework.registry_adapter.OutboxWriter") as MockOutbox,
    ):
        mock_merger = AsyncMock()
        # First item upserts, second raises a shape-drift error in the write phase.
        mock_merger.upsert = AsyncMock(side_effect=["added", KeyError("drift")])
        MockMerge.return_value = mock_merger
        MockOutbox.return_value = AsyncMock()

        counters = await adapter.run_cycle(db_session, _mock_settings())

    assert counters["items_added"] == 1
    assert counters["items_skipped"] == 1


# ──────────────────────────────────────────────────────────────────────────
# WS-8b — npm non-200 stream → success=False cursor (no silent false-green)
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_npm_non_200_writes_failure_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 429/5xx on the npm changes stream records success=False and yields nothing,
    instead of falling through to the success=True cursor write (WS-8b)."""
    from app.ingestion.config.loader import get_source_config
    from app.ingestion.framework import cursor as cursor_mod
    from app.ingestion.sources.npm import NpmAdapter

    captured: dict[str, Any] = {}

    async def _fake_read(_session: Any, _name: str) -> dict[str, Any]:
        return {"seq": 0}

    async def _fake_write(_session: Any, _name: str, _data: Any, success: bool) -> None:
        captured["success"] = success

    monkeypatch.setattr(cursor_mod, "read_cursor", _fake_read)
    monkeypatch.setattr(cursor_mod, "write_cursor", _fake_write)

    class _FakeSession:
        async def __aenter__(self) -> _FakeSession:
            return self

        async def __aexit__(self, *a: Any) -> None:
            return None

        async def commit(self) -> None:
            return None

    from app.db import session as session_mod

    monkeypatch.setattr(session_mod, "AsyncSessionLocal", lambda: _FakeSession())

    class _Stream:
        async def __aenter__(self) -> Any:
            r = MagicMock()
            r.status_code = 429
            return r

        async def __aexit__(self, *a: Any) -> None:
            return None

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=_Stream())

    adapter = NpmAdapter(get_source_config("npm"))
    items = [item async for item in adapter.list_items(mock_client)]

    assert items == []
    assert captured.get("success") is False


# ──────────────────────────────────────────────────────────────────────────
# Cycle-level — provider failure (403/429/5xx) → clean failed result, no raise
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "code,expected_reason",
    [(403, "rate_limit"), (429, "rate_limit"), (500, "http_5xx"), (503, "http_5xx")],
)
@pytest.mark.asyncio
async def test_cycle_provider_failure_warns_no_raise(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    code: int,
    expected_reason: str,
) -> None:
    """A provider HTTP error out of run_cycle is classified to a clean failed result
    WITHOUT re-raising (no traceback, no retry storm) and does NOT flip `blocked`."""
    from app.core import config as config_module
    from app.db import session as session_module
    from app.ingestion import tasks as tasks_module
    from app.ingestion.config.loader import get_source_config
    from app.ingestion.sources.smithery import SmitheryAdapter
    from app.ingestion.tasks import run_source_cycle

    monkeypatch.setattr(config_module.get_settings(), "ingestion_source_blocklist", [])

    req = httpx.Request("GET", "https://api.github.com/search/repositories")
    resp = httpx.Response(code, request=req)
    adapter = SmitheryAdapter(get_source_config("smithery"))
    adapter.run_cycle = AsyncMock(  # type: ignore[method-assign]
        side_effect=httpx.HTTPStatusError("err", request=req, response=resp)
    )

    def _build(_name: str) -> SmitheryAdapter:
        return adapter

    monkeypatch.setattr(tasks_module, "build_adapter", _build)

    class _FakeCtx:
        async def __aenter__(self) -> AsyncSession:
            return db_session

        async def __aexit__(self, *args: object) -> None:
            pass

    monkeypatch.setattr(session_module, "AsyncSessionLocal", lambda: _FakeCtx())

    result = await run_source_cycle("smithery")
    assert result == {"skipped": "failed", "reason": expected_reason}
