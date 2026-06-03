"""Tests for RegistryAdapter.run_cycle using a mock HTTP client (no live requests)."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.config.loader import SourceConfig
from app.ingestion.framework.base_adapter import NormalizedItem, RawItem
from app.ingestion.framework.registry_adapter import RegistryAdapter

# ---------------------------------------------------------------------------
# Minimal concrete subclass for testing
# ---------------------------------------------------------------------------


class _MinimalAdapter(RegistryAdapter):
    """Minimal concrete adapter to exercise the base run_cycle logic."""

    def __init__(self, config: SourceConfig, items: list[RawItem]) -> None:
        super().__init__(config)
        self._items = items

    async def list_items(self, client: Any):
        for item in self._items:
            yield item

    def normalize(self, raw: RawItem) -> NormalizedItem | None:
        if raw.http_status != 200:
            return None
        d: dict[str, Any] = raw.payload_hint
        owner_obj: dict[str, Any] = d.get("owner") or {}
        org: str = owner_obj.get("login") or ""
        repo: str = d.get("name") or ""
        if not org or not repo:
            return None
        return NormalizedItem(
            github_org=org,
            github_repo=repo,
            display_name=repo,
            description=d.get("description") or "",
            metadata_files={},
            aggregator_listings=["test_source"],
        )


def _make_config() -> SourceConfig:
    return SourceConfig(
        name="github_topics",
        kind="api",
        hosts=["api.github.com"],
        discovery={},
    )


def _make_raw(
    org: str = "acme",
    repo: str = "skill",
    http_status: int = 200,
    from_cache: bool = False,
) -> RawItem:
    payload = {
        "name": repo,
        "owner": {"login": org},
        "description": "test",
        "html_url": f"https://github.com/{org}/{repo}",
        "stargazers_count": 0,
        "pushed_at": None,
        "default_branch": "main",
        "archived": False,
        "license": None,
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return RawItem(
        source_id=f"{org}/{repo}",
        raw_body_bytes=body,
        raw_body_hash=hashlib.sha256(body).hexdigest(),
        http_status=http_status,
        from_cache=from_cache,
        fetch_tier=1,
        payload_hint=payload,
    )


# ---------------------------------------------------------------------------
# Tests — using mocked HttpClientFactory + MergeEngine to avoid ORM bug
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_cycle_304_increments_http_304_count(
    db_session: AsyncSession,
) -> None:
    """304 items should increment http_304_count."""
    items = [_make_raw(http_status=304, from_cache=True)]
    adapter = _MinimalAdapter(_make_config(), items)

    settings = MagicMock()
    settings.hishel_db_path = ":memory:"
    settings.hishel_github_ttl_seconds = 3600
    settings.hishel_aggregator_ttl_seconds = 3600

    # Mock the HttpClientFactory so no real connection is made
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

        mock_outbox = AsyncMock()
        MockOutbox.return_value = mock_outbox

        # Patch session.commit to be a no-op
        db_session.commit = AsyncMock()

        counters = await adapter.run_cycle(db_session, settings)

    assert counters["http_304_count"] == 1
    assert counters["items_added"] == 0


@pytest.mark.asyncio
async def test_run_cycle_500_increments_http_5xx_count(
    db_session: AsyncSession,
) -> None:
    """5xx items should increment http_5xx_count."""
    items = [_make_raw(http_status=503)]
    adapter = _MinimalAdapter(_make_config(), items)

    settings = MagicMock()
    settings.hishel_db_path = ":memory:"
    settings.hishel_github_ttl_seconds = 3600
    settings.hishel_aggregator_ttl_seconds = 3600

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
        MockMerge.return_value = mock_merger
        mock_outbox = AsyncMock()
        MockOutbox.return_value = mock_outbox
        db_session.commit = AsyncMock()

        counters = await adapter.run_cycle(db_session, settings)

    assert counters["http_5xx_count"] == 1


@pytest.mark.asyncio
async def test_run_cycle_successful_item_increments_added(
    db_session: AsyncSession,
) -> None:
    """A 200 item whose normalize() returns a NormalizedItem should increment items_added."""
    items = [_make_raw(http_status=200)]
    adapter = _MinimalAdapter(_make_config(), items)

    settings = MagicMock()
    settings.hishel_db_path = ":memory:"
    settings.hishel_github_ttl_seconds = 3600
    settings.hishel_aggregator_ttl_seconds = 3600

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

        mock_outbox = AsyncMock()
        MockOutbox.return_value = mock_outbox
        db_session.commit = AsyncMock()

        counters = await adapter.run_cycle(db_session, settings)

    assert counters["items_added"] == 1
    assert counters["items_updated"] == 0


@pytest.mark.asyncio
async def test_run_cycle_updated_item_increments_updated(
    db_session: AsyncSession,
) -> None:
    """A 200 item whose merge returns 'updated' should increment items_updated."""
    items = [_make_raw(http_status=200)]
    adapter = _MinimalAdapter(_make_config(), items)

    settings = MagicMock()
    settings.hishel_db_path = ":memory:"
    settings.hishel_github_ttl_seconds = 3600
    settings.hishel_aggregator_ttl_seconds = 3600

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
        mock_merger.upsert = AsyncMock(return_value="updated")
        MockMerge.return_value = mock_merger

        mock_outbox = AsyncMock()
        MockOutbox.return_value = mock_outbox
        db_session.commit = AsyncMock()

        counters = await adapter.run_cycle(db_session, settings)

    assert counters["items_updated"] == 1
    assert counters["items_added"] == 0


@pytest.mark.asyncio
async def test_run_cycle_normalize_returns_none_skips_merge(
    db_session: AsyncSession,
) -> None:
    """When normalize() returns None, merge is skipped but outbox still appended."""
    # Use a payload that will cause normalize to return None (no owner)
    payload = {"description": "no owner"}
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    items = [
        RawItem(
            source_id="skip/item",
            raw_body_bytes=body,
            raw_body_hash=hashlib.sha256(body).hexdigest(),
            http_status=200,
            fetch_tier=1,
            payload_hint=payload,
        )
    ]
    adapter = _MinimalAdapter(_make_config(), items)

    settings = MagicMock()
    settings.hishel_db_path = ":memory:"
    settings.hishel_github_ttl_seconds = 3600
    settings.hishel_aggregator_ttl_seconds = 3600

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
        MockMerge.return_value = mock_merger

        mock_outbox = AsyncMock()
        MockOutbox.return_value = mock_outbox
        db_session.commit = AsyncMock()

        counters = await adapter.run_cycle(db_session, settings)

    assert counters["items_added"] == 0
    mock_merger.upsert.assert_not_called()
    mock_outbox.append.assert_called_once()
