"""Unit tests for scan-fetch resilience (resolve_ref + tarball extraction).

Both cover failures the durable auto-scan pipeline must NOT let bubble out as
unhandled tracebacks (which burn Procrastinate's 3 retries re-fetching the repo):

1. A 404 on the `branches/<default_branch>` endpoint (repo deleted mid-window,
   an empty repo with no commits, or a renamed branch) must raise `FetchError`,
   not the raw `httpx.HTTPStatusError` — so `execute_scan`'s `except FetchError`
   handles it cleanly (stamp recency + one INFO line).
2. A tarball member whose name is illegal on the local filesystem (a `?` /
   trailing `…` on Windows → WinError 123) must be skipped per-file, not abort
   the whole repo extraction.

GitHub calls are mocked via `httpx.MockTransport` (patched onto
`fetch.httpx.AsyncClient`); tarball extraction is exercised against an in-memory
`.tar.gz`, with `extract` patched to raise deterministically cross-platform.
"""

from __future__ import annotations

import io
import tarfile
import tempfile
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from app.scan import fetch
from app.scan.fetch import FetchError

URL = "https://github.com/acme/gone"


def _patch_client(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    real_client = httpx.AsyncClient

    def factory(*_a: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(fetch.httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_resolve_ref_branch_404_raises_fetcherror(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repo resolves (200) but `branches/main` 404s → FetchError, not HTTPStatusError."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/branches/" in url:
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(200, json={"default_branch": "main", "size": 10})

    _patch_client(monkeypatch, handler)

    with pytest.raises(FetchError, match="branch not found"):
        await fetch.resolve_ref(URL)


@pytest.mark.asyncio
async def test_resolve_ref_sha_branch_404_raises_fetcherror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tarball-path resolver mirrors the same 404 → FetchError handling."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/branches/" in url:
            return httpx.Response(404, json={"message": "Not Found"})
        return httpx.Response(200, json={"default_branch": "main", "size": 10})

    _patch_client(monkeypatch, handler)

    ref = fetch.parse_github_url(URL)
    async with httpx.AsyncClient() as client:
        with pytest.raises(FetchError, match="branch not found"):
            await fetch._resolve_ref_sha(client, ref)  # pyright: ignore[reportPrivateUsage]


def _make_tarball(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_extract_tarball_skips_unextractable_member(monkeypatch: pytest.MonkeyPatch) -> None:
    """An OSError on one member (illegal filename on the local FS) skips just that
    file — the rest of the repo still extracts, no exception propagates."""
    blob = _make_tarball(
        {
            "acme-gone-abc1234/good.md": b"# good",
            "acme-gone-abc1234/bad.md": b"# bad",
        }
    )

    def fake_extract(
        self: tarfile.TarFile, member: tarfile.TarInfo, path: object = None, **kwargs: object
    ) -> None:
        # `_extract_tarball` strips the top-level prefix, so member.name is relative.
        # The good member is a no-op (the test asserts counts, not on-disk bytes).
        if member.name == "bad.md":
            raise OSError(123, "The filename, directory name, or volume label syntax is incorrect")

    monkeypatch.setattr(tarfile.TarFile, "extract", fake_extract)

    with tempfile.TemporaryDirectory() as tmp:
        kept, skipped = fetch._extract_tarball(blob, Path(tmp))  # pyright: ignore[reportPrivateUsage]

    assert kept == 1
    assert skipped == ["bad.md"]
