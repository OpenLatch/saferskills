"""Shared fixtures for router integration tests.

`db_client` wires the in-process FastAPI app's `get_session` dependency to the
per-test SAVEPOINT-isolated `db_session`, and `seed_item` inserts a catalog
item + completed scan the item-detail / vendor tests build on. Both depend on a
live Postgres (the `test-be` CI lane provides one); pure-JWT tests in
`test_vendor.py` skip these and need no DB.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.main import app
from app.models.catalog_item import CatalogItem
from app.models.scan import Finding, Scan


@pytest_asyncio.fixture
async def db_session(db_engine: Any) -> AsyncIterator[AsyncSession]:
    """Override the root `db_session` with true SAVEPOINT isolation.

    The router endpoints call `session.commit()`. With `join_transaction_mode=
    "create_savepoint"`, each commit releases a SAVEPOINT nested inside one
    outer transaction that is rolled back at teardown — so committed rows never
    escape, and unique-constraint collisions across tests can't happen.
    """
    async with db_engine.connect() as conn:  # pyright: ignore[reportUnknownMemberType]
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()


@pytest_asyncio.fixture
async def db_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """AsyncClient whose API requests share the test's rolled-back session.

    The endpoints call `session.commit()`; against the SAVEPOINT-wrapped test
    session that flushes-and-keeps within the outer transaction, which the
    fixture rolls back at teardown — so no test data escapes.
    """

    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest_asyncio.fixture
async def seed_item(db_session: AsyncSession) -> tuple[CatalogItem, Scan]:
    """Insert a catalog item + one completed scan with a single finding."""
    suffix = uuid.uuid4().hex[:8]
    item = CatalogItem(
        kind="mcp_server",
        slug=f"acme--widget-{suffix}",
        display_name="Acme Widget",
        github_url="https://github.com/acme/widget",
        github_org="acme",
        github_repo="widget",
        default_branch="main",
        popularity_tier="indexed",
        popularity_score=42,
        agent_compatibility=["claude-code", "cursor", "codex"],
        sources=[],
    )
    db_session.add(item)
    await db_session.flush()

    scan = Scan(
        catalog_item_id=item.id,
        idempotency_key=uuid.uuid4().hex,
        github_url=item.github_url,
        ref_sha="a" * 40,
        aggregate_score=87,
        tier="green",
        sub_scores={
            "security": 92,
            "supply_chain": 80,
            "maintenance": 85,
            "transparency": 88,
            "community": 90,
        },
        score_breakdown={"aggregate_math": {"formula": "0.35*92 + ...", "tier_mapping": "green"}},
        rubric_version="abc1234",
        engine_version="def5678",
        latency_ms=2400,
        source="submission",
        scanned_at=datetime.now(tz=UTC),
    )
    db_session.add(scan)
    await db_session.flush()

    finding = Finding(
        scan_id=scan.id,
        rule_id="SS-MCP-POISON-UNICODE-TAG-01",
        severity="high",
        sub_score="security",
        penalty=12,
        status_at_scan="active",
        file_path="server.py",
        line_start=10,
        line_end=12,
        matched_content_sha256="f" * 64,
        remediation_link="https://example.com/fix",
        rubric_version="abc1234",
    )
    db_session.add(finding)
    await db_session.flush()

    return item, scan
