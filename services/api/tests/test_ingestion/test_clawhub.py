"""Public ClawHub API contract regressions (official docs + observed empty cursor page)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.config.loader import get_source_config
from app.ingestion.framework.base_adapter import RawItem, build_adapter
from app.ingestion.sources.clawhub import ClawhubAdapter
from app.models import CrawlerCursor

# Shape documented at https://docs.openclaw.ai/clawhub/http-api#get-apiv1skills.
_RECORD: dict[str, Any] = {
    "ownerHandle": "steipete",
    "slug": "gifgrep",
    "displayName": "GifGrep",
    "summary": "Search and download GIFs.",
    "topics": ["Productivity"],
    "tags": {"latest": "1.2.3"},
    "stats": {"downloads": 42},
    "createdAt": 1770000000000,
    "updatedAt": 1790000000000,
    "latestVersion": {"version": "1.2.3", "createdAt": 1790000000000, "changelog": "Update"},
    "metadata": {"os": ["macos"], "systems": ["aarch64-darwin"]},
}


def _adapter(**discovery: Any) -> ClawhubAdapter:
    config = get_source_config("clawhub")
    return ClawhubAdapter(
        config.model_copy(update={"discovery": {**config.discovery, **discovery}})
    )


def _raw(record: dict[str, Any], status: int = 200) -> RawItem:
    body = json.dumps(record).encode()
    return RawItem(
        "clawhub/test",
        body,
        hashlib.sha256(body).hexdigest(),
        http_status=status,
        payload_hint=record,
    )


async def test_empty_short_pages_continue_and_owner_identity_is_preserved() -> None:
    pages: list[dict[str, Any]] = [
        {"items": [], "nextCursor": "opaque-page-2"},
        {"items": [_RECORD], "nextCursor": "opaque-page-3"},
        {"items": [_RECORD, {**_RECORD, "ownerHandle": "another-publisher"}], "nextCursor": None},
    ]
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=pages[len(requests) - 1])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        items = [item async for item in _adapter().list_items(client)]
    assert len(items) == 2
    assert [request.url.params.get("cursor") for request in requests] == [
        None,
        "opaque-page-2",
        "opaque-page-3",
    ]
    assert all(request.url.host == "clawhub.ai" for request in requests)
    assert all(request.url.params["sort"] == "createdAt" for request in requests)
    assert items[0].source_id == "clawhub/https://clawhub.ai/steipete/skills/gifgrep"
    assert items[1].source_id == "clawhub/https://clawhub.ai/another-publisher/skills/gifgrep"
    assert items[0].raw_body_hash == hashlib.sha256(items[0].raw_body_bytes).hexdigest()


def test_normalizes_public_listing_without_inventing_github_coordinates() -> None:
    normalized = _adapter().normalize(_raw(_RECORD))
    assert normalized is not None
    assert normalized.registry_item_id == "steipete/gifgrep"
    assert normalized.source_url == "https://clawhub.ai/steipete/skills/gifgrep"
    assert normalized.display_name == "GifGrep"
    assert normalized.description == "Search and download GIFs."
    assert normalized.github_org is normalized.github_repo is normalized.github_url is None
    assert normalized.kind == "skill"
    assert normalized.aggregator_listings == ["clawhub"]
    assert normalized.metadata_files == {}


@pytest.mark.parametrize(
    "record",
    [
        {**_RECORD, "ownerHandle": "../private"},
        {**_RECORD, "slug": "name?token=private"},
        {**_RECORD, "ownerHandle": None},
        {**_RECORD, "latestVersion": None},
    ],
)
def test_skips_invalid_identity_or_no_public_version(record: dict[str, Any]) -> None:
    assert _adapter().normalize(_raw(record)) is None


def test_normalization_bounds_text_and_skips_http_errors() -> None:
    normalized = _adapter().normalize(
        _raw({**_RECORD, "displayName": "x" * 300, "summary": "y" * 400})
    )
    assert normalized is not None
    assert len(normalized.display_name) == 200
    assert len(normalized.description) == 280
    assert _adapter().normalize(_raw(_RECORD, 503)) is None


async def test_item_budget_stops_without_requesting_another_page() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"items": [_RECORD], "nextCursor": "more"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        items = [item async for item in _adapter(max_items=1).list_items(client)]
    assert len(items) == len(requests) == 1
    assert requests[0].url.params["limit"] == "1"


async def test_empty_pages_are_bounded() -> None:
    count = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        return httpx.Response(200, json={"items": [], "nextCursor": str(count)})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        items = [item async for item in _adapter(max_pages=2).list_items(client)]
    assert items == []
    assert count == 2


async def test_repeated_cursor_fails_instead_of_looping() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"items": [], "nextCursor": "repeat"})
        )
    ) as client:
        with pytest.raises(ValueError, match="Repeated ClawHub"):
            _ = [item async for item in _adapter().list_items(client)]


@pytest.mark.parametrize("status", [429, 503])
async def test_http_failure_is_not_a_successful_empty_catalog(status: int) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                status, text="Rate limit or upstream failure", headers={"Retry-After": "60"}
            )
        )
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            _ = [item async for item in _adapter().list_items(client)]


def test_config_keeps_registry_and_queue_but_uses_only_public_api_host() -> None:
    adapter = build_adapter("clawhub")
    assert isinstance(adapter, ClawhubAdapter)
    assert adapter.config.registry_id == "clawhub"
    assert adapter.config.kind == "api"
    assert adapter.config.hosts == ["clawhub.ai"]
    assert adapter.config.queue == "ingest_aggregator"
    assert adapter.config.rate_limit_per_second == 1


async def test_checkpoint_resumes_only_after_committed_chunk_and_marks_exhaustion(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.ingestion.framework.cursor import read_cursor, save_cursor_progress
    from app.ingestion.framework.http_client import HttpClientFactory

    await save_cursor_progress(db_session, "clawhub", {})
    await db_session.execute(
        update(CrawlerCursor)
        .where(CrawlerCursor.source == "clawhub")
        .values(
            last_successful_cycle_at=None,
            last_attempted_cycle_at=None,
            consecutive_failure_count=3,
        )
    )
    await db_session.commit()
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert not db_session.in_transaction()
        requests.append(request)
        cursor = request.url.params.get("cursor")
        return httpx.Response(
            200,
            json={
                "items": [{**_RECORD, "ownerHandle": "checkpoint-test", "slug": cursor or "first"}],
                "nextCursor": "second" if cursor is None else None,
            },
        )

    def build_client(*args: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handle))

    monkeypatch.setattr(HttpClientFactory, "build", build_client)
    first = await _adapter(max_items=1).run_cycle(db_session, object())
    assert first["items_added"] == 1
    assert await read_cursor(db_session, "clawhub") == {
        "next_cursor": "second",
        "completed": False,
    }
    health = (
        await db_session.execute(select(CrawlerCursor).where(CrawlerCursor.source == "clawhub"))
    ).scalar_one()
    assert health.last_successful_cycle_at is not None
    assert health.last_attempted_cycle_at is not None
    assert health.consecutive_failure_count == 0
    second = await _adapter(max_items=1).run_cycle(db_session, object())
    assert second["items_added"] == 1
    assert await read_cursor(db_session, "clawhub") == {
        "next_cursor": None,
        "completed": True,
    }
    assert [request.url.params.get("cursor") for request in requests] == [None, "second"]


async def test_failed_chunk_does_not_advance_durable_cursor(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.ingestion.framework.cursor import read_cursor, save_cursor_progress
    from app.ingestion.framework.http_client import HttpClientFactory

    initial = {"next_cursor": "resume-here", "completed": False}
    await save_cursor_progress(db_session, "clawhub", initial)
    await db_session.commit()
    requests = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        if requests == 2:
            raise httpx.ReadTimeout("upstream timeout", request=request)
        return httpx.Response(
            200,
            json={"items": [_RECORD], "nextCursor": "not-committed-yet"},
        )

    def build_client(*args: Any) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handle))

    monkeypatch.setattr(HttpClientFactory, "build", build_client)
    with pytest.raises(httpx.ReadTimeout):
        await _adapter().run_cycle(db_session, object())
    assert await read_cursor(db_session, "clawhub") == initial


async def test_empty_page_budget_preserves_resume_cursor() -> None:
    adapter = _adapter(max_pages=1)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"items": [], "nextCursor": "resume"})
        )
    ) as client:
        assert [item async for item in adapter.list_items(client)] == []
    assert adapter.next_cursor == "resume"
    assert not adapter.completed


async def test_oversized_page_fails_without_skipping_records() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"items": [_RECORD, _RECORD], "nextCursor": "more"},
            )
        )
    ) as client:
        with pytest.raises(ValueError, match="exceeded requested page limit"):
            _ = [item async for item in _adapter(max_items=1).list_items(client)]
