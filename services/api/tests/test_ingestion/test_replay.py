"""Tests for app.ingestion.replay — replayability invariant.

NOTE: Integration tests that call StubAdapter.run_cycle are xfail due to the
ORM column name mismatch documented in test_merger.py. The pure-function tests
for _hash_from_payload and _normalized_from_payload are always green.
"""

from __future__ import annotations

import datetime as dt
import hashlib

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.ingestion.config.loader import SourceConfig
from app.ingestion.replay import (
    _hash_from_payload,  # pyright: ignore[reportPrivateUsage,reportUnknownVariableType]
    _normalized_from_payload,  # pyright: ignore[reportPrivateUsage,reportUnknownVariableType]
)
from app.ingestion.sources.stub import StubAdapter
from tests.test_ingestion.conftest import SAMPLE_REPO

# ---------------------------------------------------------------------------
# Pure-function tests (no DB)
# ---------------------------------------------------------------------------


class TestHashFromPayload:
    def test_empty_file_hashes_returns_sha256_of_empty(self) -> None:
        result = _hash_from_payload({"metadata_file_hashes": {}})
        assert result == hashlib.sha256(b"").hexdigest()

    def test_omitted_key_is_excluded(self) -> None:
        result = _hash_from_payload({"metadata_file_hashes": {"_omitted": "payload-too-large"}})
        assert result == hashlib.sha256(b"").hexdigest()

    def test_real_file_hash_produces_deterministic_result(self) -> None:
        payload = {
            "metadata_file_hashes": {
                "SKILL.md": "a" * 64,
                "README.md": "b" * 64,
            }
        }
        r1 = _hash_from_payload(payload)
        r2 = _hash_from_payload(payload)
        assert r1 == r2

    def test_hash_is_order_invariant(self) -> None:
        a = _hash_from_payload(
            {"metadata_file_hashes": {"SKILL.md": "a" * 64, "README.md": "b" * 64}}
        )
        b = _hash_from_payload(
            {"metadata_file_hashes": {"README.md": "b" * 64, "SKILL.md": "a" * 64}}
        )
        assert a == b


class TestNormalizedFromPayload:
    def test_basic_fields(self) -> None:
        payload = {
            "github_org": "acme",
            "github_repo": "skill-1",
            "display_name": "skill-1",
            "description": "desc",
            "license_spdx": "MIT",
        }
        n = _normalized_from_payload(payload)
        assert n.github_org == "acme"
        assert n.github_repo == "skill-1"
        assert n.display_name == "skill-1"
        assert n.license_spdx == "MIT"

    def test_missing_fields_default_gracefully(self) -> None:
        n = _normalized_from_payload({"display_name": "orphan"})
        assert n.github_org is None
        assert n.github_repo is None
        assert n.description == ""
        assert n.repo_archived is False

    def test_repo_archived_coerced_to_bool(self) -> None:
        n = _normalized_from_payload({"display_name": "x", "repo_archived": 1})
        assert n.repo_archived is True


# ---------------------------------------------------------------------------
# Integration test: run_cycle → replay re-creates rows
#
# replay() opens its own AsyncSessionLocal, so we need committed data. We run
# the stub cycle (which commits inside run_cycle) and then call replay(). The
# test's db_session rollback cleans up at teardown, but replay's own session
# rolls back too (apply=False), so the catalog cleanup is double-safe.
# ---------------------------------------------------------------------------


def _stub_config() -> SourceConfig:
    return SourceConfig(
        name="github_topics",
        kind="api",
        hosts=["api.github.com", "raw.githubusercontent.com"],
        discovery={"items": [SAMPLE_REPO]},
    )


@pytest.mark.asyncio
async def test_replay_re_applies_events(db_session: AsyncSession) -> None:
    """After a stub cycle, replay re-derives at least one catalog row from events.

    `replay` runs inside the test's transaction (session-injection seam) so it sees
    the cycle's ingestion_events without a separate connection / the unmigrated dev DB.
    """
    since = dt.datetime.now(tz=dt.UTC) - dt.timedelta(seconds=5)
    await StubAdapter(_stub_config()).run_cycle(db_session, get_settings())

    from app.ingestion.replay import replay

    counts = await replay(since, apply=False, session=db_session)
    assert counts["events"] >= 1
    # Re-applying onto rows the cycle already created yields 'updated' (same slug).
    assert counts["added"] + counts["updated"] >= 1


@pytest.mark.asyncio
async def test_replay_apply_true_adds_rows(db_session: AsyncSession) -> None:
    """With the catalog cleared, replay(apply=True) re-creates rows from events alone."""
    since = dt.datetime.now(tz=dt.UTC) - dt.timedelta(seconds=5)
    await StubAdapter(_stub_config()).run_cycle(db_session, get_settings())

    from app.ingestion.replay import replay
    from app.models import CatalogItem

    # Clear the catalog the cycle created (events remain) so replay must rebuild it.
    await db_session.execute(delete(CatalogItem))
    await db_session.flush()

    counts = await replay(since, apply=True, session=db_session)
    assert counts["added"] >= 1

    rows = (await db_session.execute(select(CatalogItem))).scalars().all()
    assert len(rows) >= 1
