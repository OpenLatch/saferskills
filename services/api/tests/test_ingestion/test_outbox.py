"""Tests for app.ingestion.framework.outbox.OutboxWriter."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.framework.outbox import OutboxWriter
from app.models import IngestionEvent
from tests.test_ingestion.conftest import make_normalized, make_raw


@pytest.mark.asyncio
async def test_append_writes_one_row(db_session: AsyncSession) -> None:
    writer = OutboxWriter(db_session, source="github_topics")
    raw = make_raw(source_id="acme/skill-1", http_status=200)
    normalized = make_normalized(display_name="skill-1", metadata_files={"SKILL.md": b"# hi"})
    await writer.append(raw, normalized, applied=True)
    await db_session.flush()

    rows = (await db_session.execute(select(IngestionEvent))).scalars().all()
    assert len(rows) == 1
    evt = rows[0]
    assert evt.source == "github_topics"
    assert evt.source_id == "acme/skill-1"
    assert evt.http_status == 200
    assert evt.applied_at is not None


@pytest.mark.asyncio
async def test_append_applied_false_leaves_applied_at_null(db_session: AsyncSession) -> None:
    writer = OutboxWriter(db_session, source="github_topics")
    raw = make_raw(source_id="acme/skill-2")
    normalized = make_normalized(display_name="skill-2")
    await writer.append(raw, normalized, applied=False)
    await db_session.flush()

    rows = (await db_session.execute(select(IngestionEvent))).scalars().all()
    assert len(rows) == 1
    assert rows[0].applied_at is None


@pytest.mark.asyncio
async def test_payload_contains_metadata_file_hashes_not_bytes(
    db_session: AsyncSession,
) -> None:
    """Payload must store per-file SHA-256 hashes, never raw bytes."""
    file_content = b"# SKILL.md content"
    expected_hash = hashlib.sha256(file_content).hexdigest()

    writer = OutboxWriter(db_session, source="github_topics")
    raw = make_raw(source_id="acme/skill-3")
    normalized = make_normalized(
        display_name="skill-3",
        metadata_files={"SKILL.md": file_content, "mcp.json": b'{"transport":"stdio"}'},
    )
    await writer.append(raw, normalized, applied=True)
    await db_session.flush()

    row = (await db_session.execute(select(IngestionEvent))).scalar_one()
    payload = row.payload
    assert payload is not None

    file_hashes = payload.get("metadata_file_hashes", {})
    # Hashes must be present — not raw bytes
    assert "SKILL.md" in file_hashes
    assert file_hashes["SKILL.md"] == expected_hash
    # No raw bytes in the payload
    assert not any(isinstance(v, bytes) for v in file_hashes.values())


@pytest.mark.asyncio
async def test_append_normalized_none_stores_null_payload(db_session: AsyncSession) -> None:
    writer = OutboxWriter(db_session, source="github_topics")
    raw = make_raw(source_id="acme/skip-me", http_status=404)
    await writer.append(raw, None, applied=True)
    await db_session.flush()

    row = (await db_session.execute(select(IngestionEvent))).scalar_one()
    assert row.payload is None


@pytest.mark.asyncio
async def test_multiple_appends_produce_multiple_rows(db_session: AsyncSession) -> None:
    writer = OutboxWriter(db_session, source="github_topics")
    for i in range(3):
        raw = make_raw(source_id=f"acme/skill-{i}")
        normalized = make_normalized(display_name=f"skill-{i}")
        await writer.append(raw, normalized, applied=True)
    await db_session.flush()

    rows = (await db_session.execute(select(IngestionEvent))).scalars().all()
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_payload_has_expected_fields(db_session: AsyncSession) -> None:
    writer = OutboxWriter(db_session, source="github_topics")
    raw = make_raw(source_id="acme/fields-check")
    normalized = make_normalized(
        github_org="acme",
        github_repo="fields-check",
        display_name="fields-check",
        description="testing payload fields",
        stars=42,
    )
    await writer.append(raw, normalized, applied=True)
    await db_session.flush()

    row = (await db_session.execute(select(IngestionEvent))).scalar_one()
    payload = row.payload
    assert payload is not None
    for key in ("github_org", "github_repo", "display_name", "description", "stars"):
        assert key in payload, f"missing key: {key}"
    assert payload["github_org"] == "acme"
    assert payload["stars"] == 42
