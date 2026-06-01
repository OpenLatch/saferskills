"""Tests for the cached GitHub repository-metadata fetcher.

Mirrors the github-stars proxy test style: a monkeypatched httpx client returns
canned responses; success populates all fields + caches, timeout degrades to
empty fields.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.services import repository_metadata as rm


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    """URL-aware fake — the metadata service calls /repos then /releases/latest."""

    def __init__(self, *, exc: Exception | None = None) -> None:
        self._exc = exc

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, url: str, *_: object, **__: object) -> _FakeResponse:
        if self._exc is not None:
            raise self._exc
        if url.endswith("/releases/latest"):
            return _FakeResponse(200, {"tag_name": "v1.3.1"})
        return _FakeResponse(
            200,
            {
                "stargazers_count": 2340,
                "forks_count": 184,
                "description": "Extract structured data from PDFs.",
                "default_branch": "main",
                "license": {"spdx_id": "Apache-2.0"},
            },
        )


@pytest.mark.asyncio
async def test_repo_metadata_success_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    rm.reset_cache()
    calls = {"n": 0}

    def _factory(*_: object, **__: object) -> _FakeClient:
        calls["n"] += 1
        return _FakeClient()

    monkeypatch.setattr(rm.httpx, "AsyncClient", _factory)
    meta = await rm.get_repository_metadata("fieldwork", "pdf-extract")
    assert meta.stars == 2340
    assert meta.forks == 184
    assert meta.license_spdx == "Apache-2.0"
    assert meta.latest_version == "v1.3.1"
    assert meta.default_branch == "main"

    # Second call served from the ~1h cache — no new client.
    again = await rm.get_repository_metadata("fieldwork", "pdf-extract")
    assert again.latest_version == "v1.3.1"
    assert calls["n"] == 1
    rm.reset_cache()


@pytest.mark.asyncio
async def test_repo_metadata_timeout_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    rm.reset_cache()

    def _factory(*_: object, **__: object) -> _FakeClient:
        return _FakeClient(exc=httpx.ConnectTimeout("timed out"))

    monkeypatch.setattr(rm.httpx, "AsyncClient", _factory)
    meta = await rm.get_repository_metadata("acme", "widget")
    assert meta.stars is None
    assert meta.license_spdx is None
    assert meta.latest_version is None
    rm.reset_cache()


@pytest.mark.asyncio
async def test_repo_metadata_noassertion_license_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    rm.reset_cache()

    class _NoLicenseClient(_FakeClient):
        async def get(self, url: str, *_: object, **__: object) -> _FakeResponse:
            if url.endswith("/releases/latest"):
                return _FakeResponse(404, {})
            return _FakeResponse(
                200, {"stargazers_count": 1, "license": {"spdx_id": "NOASSERTION"}}
            )

    def _make_client(*_: object, **__: object) -> _NoLicenseClient:
        return _NoLicenseClient()

    monkeypatch.setattr(rm.httpx, "AsyncClient", _make_client)
    meta = await rm.get_repository_metadata("acme", "unlicensed")
    assert meta.stars == 1
    assert meta.license_spdx is None
    assert meta.latest_version is None
    rm.reset_cache()
