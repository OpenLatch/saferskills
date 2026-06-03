"""Ingestion-local fixtures and factories shared across the test_ingestion suite."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.framework.base_adapter import NormalizedItem, RawItem


@pytest_asyncio.fixture
async def db_session(db_engine: Any) -> AsyncIterator[AsyncSession]:
    """Per-test session isolated by an outer connection-level transaction + SAVEPOINT.

    Overrides the parent conftest's plain begin()/rollback() session. Ingestion code
    (e.g. RegistryAdapter.run_cycle) calls `session.commit()`, which under the plain
    fixture durably commits to the shared test DB and leaks rows across tests. With
    `join_transaction_mode="create_savepoint"` every inner commit() releases a SAVEPOINT
    while the outer connection transaction stays open, so the teardown rollback undoes
    everything — true per-test isolation even for committing code.
    """
    conn = await db_engine.connect()
    trans = await conn.begin()
    session = AsyncSession(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    try:
        yield session
    finally:
        await session.close()
        if trans.is_active:
            await trans.rollback()
        await conn.close()


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def make_raw(
    *,
    source_id: str = "acme/test-skill",
    http_status: int = 200,
    payload_hint: dict[str, Any] | None = None,
    **kwargs: Any,
) -> RawItem:
    """Build a minimal RawItem for test use."""
    import hashlib
    import json

    body: dict[str, Any] = payload_hint or {"name": "test-skill"}
    raw_bytes = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    return RawItem(
        source_id=source_id,
        raw_body_bytes=raw_bytes,
        raw_body_hash=hashlib.sha256(raw_bytes).hexdigest(),
        http_status=http_status,
        fetch_tier=1,
        payload_hint=body,
        **kwargs,
    )


def make_normalized(
    *,
    github_org: str | None = "acme",
    github_repo: str | None = "test-skill",
    display_name: str = "test-skill",
    description: str = "A test skill",
    kind: str | None = None,
    stars: int = 0,
    metadata_files: dict[str, bytes] | None = None,
    source_url: str | None = None,
    **kwargs: Any,
) -> NormalizedItem:
    """Build a minimal NormalizedItem for test use."""
    default_url = (
        f"https://github.com/{github_org}/{github_repo}" if github_org and github_repo else None
    )
    return NormalizedItem(
        github_org=github_org,
        github_repo=github_repo,
        display_name=display_name,
        description=description,
        kind=kind,
        stars=stars,
        github_url=default_url,
        source_url=source_url if source_url is not None else default_url,
        metadata_files=metadata_files or {},
        aggregator_listings=["github_topics"],
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Representative repo-JSON dict (GitHub Topics API shape used by StubAdapter)
# ---------------------------------------------------------------------------

SAMPLE_REPO: dict[str, Any] = {
    "id": 123456,
    "name": "my-skill",
    "full_name": "testorg/my-skill",
    "owner": {"login": "testorg", "type": "Organization"},
    "html_url": "https://github.com/testorg/my-skill",
    "description": "A handy skill for testing",
    "stargazers_count": 10,
    "pushed_at": "2025-01-01T00:00:00Z",
    "default_branch": "main",
    "archived": False,
    "license": {"spdx_id": "MIT"},
}


@pytest.fixture
def sample_repo() -> dict[str, Any]:
    return dict(SAMPLE_REPO)
