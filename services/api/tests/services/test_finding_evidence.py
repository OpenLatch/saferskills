"""Tests for `app.services.finding_evidence` — per-finding evidence excerpts.

DB-backed (runs in `test-be` against Postgres). Covers excerpt extraction, the
hit/context line window, line + span truncation, the missing-bytes fallback
(binary/oversize sentinel + absent path + line beyond EOF), and the run-level
merge across capabilities.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact_blob import ArtifactBlob
from app.models.catalog_item import CatalogItem
from app.models.scan import Finding, Scan
from app.services.finding_evidence import (
    resolve_finding_excerpts,
    resolve_run_evidence,
)


async def _store(session: AsyncSession, files: dict[str, bytes | None]) -> dict[str, str | None]:
    """Insert blobs (None = binary/oversize sentinel) → {path: sha|None} map."""
    file_map: dict[str, str | None] = {}
    for path, content in files.items():
        if content is None:
            file_map[path] = None
            continue
        sha = hashlib.sha256(content).hexdigest()
        if not (
            await session.execute(select(ArtifactBlob).where(ArtifactBlob.sha256 == sha))
        ).scalar_one_or_none():
            session.add(
                ArtifactBlob(sha256=sha, content=content, byte_size=len(content), is_binary=False)
            )
        file_map[path] = sha
    await session.flush()
    return file_map


async def _seed_scan(
    session: AsyncSession, files: dict[str, bytes | None]
) -> tuple[CatalogItem, Scan]:
    suffix = uuid.uuid4().hex[:8]
    item = CatalogItem(
        kind="skill",
        slug=f"evid--demo-{suffix}",
        display_name="Evidence Demo",
        github_url=f"https://github.com/evid/demo-{suffix}",
        github_org="evid",
        github_repo=f"demo-{suffix}",
        default_branch="main",
        popularity_tier="indexed",
        popularity_score=10,
        sources=[],
    )
    session.add(item)
    await session.flush()

    file_map = await _store(session, files)
    scan = Scan(
        catalog_item_id=item.id,
        idempotency_key=uuid.uuid4().hex,
        github_url=item.github_url,
        ref_sha="a" * 40,
        aggregate_score=80,
        tier="green",
        sub_scores={
            "security": 80,
            "supply_chain": 80,
            "maintenance": 80,
            "transparency": 80,
            "community": 80,
        },
        score_breakdown={},
        file_hashes=file_map,
        rubric_version="abc1234",
        engine_version="def5678",
        latency_ms=100,
        source="submission",
        scanned_at=datetime.now(tz=UTC),
    )
    session.add(scan)
    await session.flush()
    return item, scan


def _finding(
    scan: Scan, *, file_path: str, line_start: int, line_end: int | None = None
) -> Finding:
    return Finding(
        scan_id=scan.id,
        rule_id="SS-SKILL-INJECT-FENCED-RUN-01",
        severity="high",
        sub_score="security",
        penalty=20,
        status_at_scan="active",
        file_path=file_path,
        line_start=line_start,
        line_end=line_end,
        matched_content_sha256="f" * 64,
        remediation_link="https://example.com/fix",
        rubric_version="abc1234",
    )


# ── excerpt extraction ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_excerpt_marks_hit_line_and_context(db_session: AsyncSession) -> None:
    body = b"line1\nline2\nTARGET line3\nline4\nline5\n"
    _item, scan = await _seed_scan(db_session, {"SKILL.md": body})
    f = _finding(scan, file_path="SKILL.md", line_start=3)
    db_session.add(f)
    await db_session.flush()

    out = await resolve_finding_excerpts(db_session, scan, [f])

    excerpt = out[str(f.id)]
    assert excerpt["file"] == "SKILL.md"
    assert excerpt["lang"] == "markdown"
    assert excerpt["truncated"] is False
    lines = excerpt["lines"]
    # context ±2 around line 3 → lines 1..5
    assert [ln["line_no"] for ln in lines] == [1, 2, 3, 4, 5]
    hit = [ln for ln in lines if ln["hit"]]
    assert len(hit) == 1
    assert hit[0]["line_no"] == 3
    assert hit[0]["text"] == "TARGET line3"


@pytest.mark.asyncio
async def test_multi_line_span_flags_each_hit_line(db_session: AsyncSession) -> None:
    body = b"a\nb\nc\nd\ne\nf\n"
    _item, scan = await _seed_scan(db_session, {"SKILL.md": body})
    f = _finding(scan, file_path="SKILL.md", line_start=2, line_end=4)
    db_session.add(f)
    await db_session.flush()

    excerpt = (await resolve_finding_excerpts(db_session, scan, [f]))[str(f.id)]
    hit_lines = [ln["line_no"] for ln in excerpt["lines"] if ln["hit"]]
    assert hit_lines == [2, 3, 4]


@pytest.mark.asyncio
async def test_verbatim_bytes_preserve_invisible_chars(db_session: AsyncSession) -> None:
    # A zero-width space must survive into the excerpt for the frontend to reveal.
    body = "deploy​ now\n".encode()
    _item, scan = await _seed_scan(db_session, {"SKILL.md": body})
    f = _finding(scan, file_path="SKILL.md", line_start=1)
    db_session.add(f)
    await db_session.flush()

    excerpt = (await resolve_finding_excerpts(db_session, scan, [f]))[str(f.id)]
    assert "​" in excerpt["lines"][0]["text"]


# ── truncation ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_huge_span_is_capped_and_marked_truncated(db_session: AsyncSession) -> None:
    body = ("\n".join(f"row{i}" for i in range(1, 41)) + "\n").encode()
    _item, scan = await _seed_scan(db_session, {"big.py": body})
    f = _finding(scan, file_path="big.py", line_start=1, line_end=40)
    db_session.add(f)
    await db_session.flush()

    excerpt = (await resolve_finding_excerpts(db_session, scan, [f]))[str(f.id)]
    assert excerpt["truncated"] is True
    assert len(excerpt["lines"]) <= 9
    assert excerpt["lang"] == "python"


@pytest.mark.asyncio
async def test_long_line_is_truncated(db_session: AsyncSession) -> None:
    body = ("x" * 500 + "\n").encode()
    _item, scan = await _seed_scan(db_session, {"f.txt": body})
    f = _finding(scan, file_path="f.txt", line_start=1)
    db_session.add(f)
    await db_session.flush()

    excerpt = (await resolve_finding_excerpts(db_session, scan, [f]))[str(f.id)]
    assert excerpt["truncated"] is True
    assert len(excerpt["lines"][0]["text"]) <= 200


# ── missing-bytes fallback ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_binary_sentinel_yields_no_excerpt(db_session: AsyncSession) -> None:
    # `None` file_hash = binary/oversize sentinel → no bytes → finding omitted.
    _item, scan = await _seed_scan(db_session, {"blob.bin": None})
    f = _finding(scan, file_path="blob.bin", line_start=1)
    db_session.add(f)
    await db_session.flush()

    out = await resolve_finding_excerpts(db_session, scan, [f])
    assert str(f.id) not in out


@pytest.mark.asyncio
async def test_absent_path_yields_no_excerpt(db_session: AsyncSession) -> None:
    _item, scan = await _seed_scan(db_session, {"SKILL.md": b"only\n"})
    f = _finding(scan, file_path="not-in-snapshot.md", line_start=1)
    db_session.add(f)
    await db_session.flush()

    out = await resolve_finding_excerpts(db_session, scan, [f])
    assert out == {}


@pytest.mark.asyncio
async def test_line_beyond_eof_yields_no_excerpt(db_session: AsyncSession) -> None:
    _item, scan = await _seed_scan(db_session, {"SKILL.md": b"one\ntwo\n"})
    f = _finding(scan, file_path="SKILL.md", line_start=99)
    db_session.add(f)
    await db_session.flush()

    out = await resolve_finding_excerpts(db_session, scan, [f])
    assert str(f.id) not in out


@pytest.mark.asyncio
async def test_empty_findings_returns_empty(db_session: AsyncSession) -> None:
    _item, scan = await _seed_scan(db_session, {"SKILL.md": b"x\n"})
    assert await resolve_finding_excerpts(db_session, scan, []) == {}


# ── run-level merge ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_run_evidence_merges_capabilities(db_session: AsyncSession) -> None:
    item_a, scan_a = await _seed_scan(db_session, {"SKILL.md": b"alpha\nhit-a\n"})
    item_b, scan_b = await _seed_scan(db_session, {"server.py": b"beta\nhit-b\n"})
    fa = _finding(scan_a, file_path="SKILL.md", line_start=2)
    fb = _finding(scan_b, file_path="server.py", line_start=2)
    db_session.add_all([fa, fb])
    await db_session.flush()

    capabilities: Sequence[tuple[Scan, CatalogItem, Sequence[Finding]]] = [
        (scan_a, item_a, [fa]),
        (scan_b, item_b, [fb]),
    ]
    out = await resolve_run_evidence(db_session, capabilities)

    assert set(out) == {str(fa.id), str(fb.id)}
    assert out[str(fa.id)]["file"] == "SKILL.md"
    assert out[str(fb.id)]["lang"] == "python"
