"""Unit tests for the IndexNow submitter + the per-run URL builder (I-07).

The httpx POST is mocked — no network. Pins: no-op without a key; correct body
shape with a key; never raises on an HTTP error; the per-run builder skips
unlisted / pending / firehose runs and includes the item slugs for a good run.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest

from app.core.config import get_settings
from app.models.catalog_item import CatalogItem
from app.models.scan import Scan
from app.models.scan_run import ScanRun
from app.seo import indexnow


class _FakeResp:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeClient:
    def __init__(self, *, resp: _FakeResp | None = None, exc: Exception | None = None) -> None:
        self._resp = resp
        self._exc = exc
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *_a: object) -> bool:
        return False

    async def post(self, url: str, json: dict[str, Any] | None = None) -> _FakeResp:
        self.calls.append((url, json or {}))
        if self._exc is not None:
            raise self._exc
        assert self._resp is not None
        return self._resp


def _patch_client(monkeypatch: pytest.MonkeyPatch, client: _FakeClient) -> None:
    def _factory(*_a: object, **_k: object) -> _FakeClient:
        return client

    monkeypatch.setattr(indexnow.httpx, "AsyncClient", _factory)


@pytest.mark.asyncio
async def test_submit_noop_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "saferskills_indexnow_key", None)
    client = _FakeClient(resp=_FakeResp(200))
    _patch_client(monkeypatch, client)
    await indexnow.submit_urls(["https://saferskills.ai/items/x"])
    assert client.calls == []  # never POSTed


@pytest.mark.asyncio
async def test_submit_noop_with_empty_url_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "saferskills_indexnow_key", "k")
    client = _FakeClient(resp=_FakeResp(200))
    _patch_client(monkeypatch, client)
    await indexnow.submit_urls([])
    assert client.calls == []


@pytest.mark.asyncio
async def test_submit_posts_correct_body(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "saferskills_indexnow_key", "secret-key")
    monkeypatch.setattr(settings, "saferskills_site_origin", "https://saferskills.ai")
    monkeypatch.setattr(
        settings, "saferskills_indexnow_key_location", "https://saferskills.ai/secret-key.txt"
    )
    client = _FakeClient(resp=_FakeResp(200))
    _patch_client(monkeypatch, client)

    await indexnow.submit_urls(["https://saferskills.ai/items/x"])

    assert len(client.calls) == 1
    url, body = client.calls[0]
    assert url == indexnow.INDEXNOW_ENDPOINT
    assert body["host"] == "saferskills.ai"
    assert body["key"] == "secret-key"
    assert body["keyLocation"] == "https://saferskills.ai/secret-key.txt"
    assert body["urlList"] == ["https://saferskills.ai/items/x"]


@pytest.mark.asyncio
async def test_submit_swallows_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "saferskills_indexnow_key", "k")
    _patch_client(monkeypatch, _FakeClient(exc=httpx.ConnectTimeout("boom")))
    # Must not raise.
    await indexnow.submit_urls(["https://saferskills.ai/items/x"])


@pytest.mark.asyncio
async def test_submit_swallows_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "saferskills_indexnow_key", "k")
    _patch_client(monkeypatch, _FakeClient(resp=_FakeResp(403)))
    await indexnow.submit_urls(["https://saferskills.ai/items/x"])  # logged, not raised


def _run(
    *, visibility: str = "public", status: str = "completed", source: str = "submission"
) -> ScanRun:
    # A duck-typed stand-in for a ScanRun row — `indexnow_urls_for_run` reads only
    # id / visibility / status / source. Cast so the strict checker accepts it.
    stub = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        visibility=visibility,
        status=status,
        source=source,
    )
    return cast(ScanRun, stub)


def test_urls_for_public_completed_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "saferskills_site_origin", "https://saferskills.ai")
    urls = indexnow.indexnow_urls_for_run(_run(), ["acme--widget"])
    assert urls == [
        "https://saferskills.ai/scans/11111111-1111-1111-1111-111111111111",
        "https://saferskills.ai/items/acme--widget",
    ]


@pytest.mark.parametrize(
    "run",
    [
        _run(visibility="unlisted"),
        _run(status="pending"),
        _run(status="failed"),
        _run(source="ingestion"),
        _run(source="rescan_rules"),
    ],
)
def test_urls_empty_for_excluded_runs(run: ScanRun) -> None:
    assert indexnow.indexnow_urls_for_run(run, ["acme--widget"]) == []


def _scan(*, tier: str = "green", source: str = "rescan_appeal") -> Scan:
    return cast(Scan, SimpleNamespace(id="s1", tier=tier, source=source))


def _item(*, visibility: str = "public", archived: bool = False, slug: str = "acme--widget"):
    return cast(CatalogItem, SimpleNamespace(slug=slug, visibility=visibility, archived=archived))


def test_scan_urls_for_public_appeal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "saferskills_site_origin", "https://saferskills.ai")
    assert indexnow.indexnow_urls_for_scan(_scan(), _item()) == [
        "https://saferskills.ai/items/acme--widget"
    ]


@pytest.mark.parametrize(
    ("scan", "item"),
    [
        (_scan(), None),  # no item
        (_scan(), _item(visibility="unlisted")),  # shadow item
        (_scan(), _item(archived=True)),  # archived item
        (_scan(tier="unscoped"), _item()),  # not completed
        (_scan(source="ingestion"), _item()),  # firehose
        (_scan(source="rescan_rules"), _item()),  # firehose
    ],
)
def test_scan_urls_empty_for_excluded(scan: Scan, item: CatalogItem | None) -> None:
    assert indexnow.indexnow_urls_for_scan(scan, item) == []
