"""Unit tests for upload extraction + identity (I-3.5, no DB).

Covers the §13.2 rejection matrix (every bucketed `(status, code, reason)`),
the happy single-file + `.zip` paths, kind/name detection, the per-capability
slug builders + grammar conformance, the public/unlisted idempotency keys, and
the engine-regression guard for `run_repo_scan_from_index`.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import AsyncIterator

import pytest

from app.core.config import get_settings
from app.scan import persistence
from app.scan.engine import run_repo_scan_from_index
from app.scan.upload import (
    UploadRejected,
    extract_upload,
    public_upload_idempotency_key,
    unlisted_idempotency_key,
    upload_content_hash,
)

# Mirrors schemas/catalog-item.schema.json `slug` pattern.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*(--[a-z0-9][a-z0-9-]*)+$")


async def _aiter(*chunks: bytes) -> AsyncIterator[bytes]:
    for c in chunks:
        yield c


def _zip(entries: dict[str, bytes], *, compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as zf:
        for path, data in entries.items():
            zf.writestr(path, data)
    return buf.getvalue()


async def _extract(body: bytes, filename: str):
    return await extract_upload(_aiter(body), filename, settings=get_settings())


# ── Happy paths ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_single_markdown_file() -> None:
    extracted = await _extract(b"---\nname: pdf-extract\n---\n# Skill", "SKILL.md")
    assert extracted.files_index == [("SKILL.md", b"---\nname: pdf-extract\n---\n# Skill")]
    assert extracted.original_filename == "SKILL.md"
    assert extracted.detected_name == "pdf-extract"
    assert extracted.detected_kind == "skill"


@pytest.mark.asyncio
async def test_valid_zip_multi_file() -> None:
    body = _zip({"skills/a/SKILL.md": b"# a", "skills/a/run.py": b"print(1)\n"})
    extracted = await _extract(body, "bundle.zip")
    paths = {p for p, _ in extracted.files_index}
    assert paths == {"skills/a/SKILL.md", "skills/a/run.py"}


@pytest.mark.asyncio
async def test_zip_skips_top_level_git_dir() -> None:
    body = _zip({".git/config": b"x", "SKILL.md": b"# y"})
    extracted = await _extract(body, "b.zip")
    assert [p for p, _ in extracted.files_index] == ["SKILL.md"]


# ── Rejection matrix (§13.2 + P1-3) ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_too_large() -> None:
    big = b"x" * (get_settings().upload_max_bytes + 1)
    with pytest.raises(UploadRejected) as ei:
        await _extract(big, "a.md")
    assert (ei.value.status, ei.value.code) == (413, "upload_too_large")


@pytest.mark.asyncio
async def test_unsupported_extension() -> None:
    with pytest.raises(UploadRejected) as ei:
        await _extract(b"hi", "a.exe")
    assert (ei.value.status, ei.value.code) == (415, "unsupported_type")


@pytest.mark.asyncio
async def test_zip_bad_magic_bytes() -> None:
    with pytest.raises(UploadRejected) as ei:
        await _extract(b"NOTAZIPHEADER", "a.zip")
    assert (ei.value.status, ei.value.code) == (415, "unsupported_type")


@pytest.mark.asyncio
async def test_binary_single_file() -> None:
    with pytest.raises(UploadRejected) as ei:
        await _extract(b"text\x00more", "a.md")
    assert (ei.value.status, ei.value.code) == (415, "binary_not_allowed")


@pytest.mark.asyncio
async def test_zip_per_file_too_big(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "upload_extract_max_per_file_bytes", 8)
    body = _zip({"a.md": b"x" * 64}, compression=zipfile.ZIP_STORED)
    with pytest.raises(UploadRejected) as ei:
        await _extract(body, "b.zip")
    assert (ei.value.status, ei.value.code, ei.value.reason) == (422, "archive_rejected", "too_big")


@pytest.mark.asyncio
async def test_zip_total_too_big(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "upload_extract_max_total_bytes", 10)
    body = _zip({"a.md": b"xxxxxx", "b.md": b"yyyyyy"}, compression=zipfile.ZIP_STORED)
    with pytest.raises(UploadRejected) as ei:
        await _extract(body, "b.zip")
    assert ei.value.reason == "too_big"


@pytest.mark.asyncio
async def test_zip_too_many_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "upload_extract_max_entries", 2)
    body = _zip({f"f{i}.md": b"x" for i in range(3)})
    with pytest.raises(UploadRejected) as ei:
        await _extract(body, "b.zip")
    assert ei.value.reason == "entries"


@pytest.mark.asyncio
async def test_zip_ratio_bomb(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "upload_extract_max_ratio", 5)
    body = _zip({"a.md": b"a" * 100_000})  # highly compressible → big ratio
    with pytest.raises(UploadRejected) as ei:
        await _extract(body, "b.zip")
    assert ei.value.reason == "ratio"


@pytest.mark.asyncio
async def test_zip_nested_archive() -> None:
    body = _zip({"inner.zip": b"PK\x03\x04rest"})
    with pytest.raises(UploadRejected) as ei:
        await _extract(body, "b.zip")
    assert ei.value.reason == "nesting"


@pytest.mark.asyncio
async def test_zip_slip_traversal() -> None:
    body = _zip({"../escape.md": b"x"})
    with pytest.raises(UploadRejected) as ei:
        await _extract(body, "b.zip")
    assert ei.value.reason == "zip_slip"


@pytest.mark.asyncio
async def test_zip_over_length_path() -> None:
    body = _zip({"a/" * 600 + "f.md": b"x"})
    with pytest.raises(UploadRejected) as ei:
        await _extract(body, "b.zip")
    assert ei.value.reason == "bad_path"


@pytest.mark.asyncio
async def test_zip_duplicate_after_fold() -> None:
    # Two entries folding to the same casefolded path.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("README.md", b"a")
        zf.writestr("readme.md", b"b")
    with pytest.raises(UploadRejected) as ei:
        await _extract(buf.getvalue(), "b.zip")
    assert ei.value.reason == "dup_path"


# ── Identity + idempotency (§13.3) ────────────────────────────────────────────


def test_content_hash_is_order_independent() -> None:
    a = upload_content_hash([("a", b"1"), ("b", b"2")])
    b = upload_content_hash([("b", b"2"), ("a", b"1")])
    assert a == b and len(a) == 64


def test_public_key_stable_unlisted_key_unique() -> None:
    ch = upload_content_hash([("a", b"1")])
    assert public_upload_idempotency_key(ch, "r1") == public_upload_idempotency_key(ch, "r1")
    # Nonce-salted → two unlisted keys for identical bytes differ (D-UP-28).
    assert unlisted_idempotency_key(ch, "r1") != unlisted_idempotency_key(ch, "r1")


# ── Slug builders + grammar (§5b) ─────────────────────────────────────────────


def test_upload_slug_grammar_and_hyphenation() -> None:
    slug = persistence.upload_capability_slug("a7b3c4d5e6", "mcp_server", "GitHub Toolbelt")
    assert slug == "upload--a7b3c4d5--mcp-server-github-toolbelt"
    assert _SLUG_RE.match(slug)


def test_unlisted_slug_grammar() -> None:
    from uuid import UUID

    slug = persistence.unlisted_capability_slug(
        UUID("3f9a1c20-0000-0000-0000-000000000000"), "skill", "pdf extract"
    )
    assert slug == "unlisted--3f9a1c20--skill-pdf-extract"
    assert _SLUG_RE.match(slug)


# ── Engine regression (§13.12) ────────────────────────────────────────────────


def test_run_repo_scan_from_index_scores_a_single_skill() -> None:
    index = [("SKILL.md", b"---\nname: t\n---\n# Title\n\nA helpful skill.\n")]
    result = run_repo_scan_from_index(index, "abc1234")
    assert result.capability_count >= 1
    assert 0 <= result.repo_aggregate_score <= 100
    assert result.ref_sha == "0" * 40
    assert result.file_count == 1
