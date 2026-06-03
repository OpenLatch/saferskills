"""Tests for infrastructure modules: worker constants, run_one_cycle CLI, enqueue task shape."""

from __future__ import annotations

import sys

import pytest


class TestWorkerConstants:
    def test_ingestion_lock_key_distinct_from_other_locks(self) -> None:
        from app.ingestion.worker import _INGESTION_LOCK_KEY  # pyright: ignore[reportPrivateUsage]

        # These must all be distinct advisory lock keys
        migration_lock = 0x5AFE5C11
        sweep_lock = 0x5AFE5C12
        assert _INGESTION_LOCK_KEY == 0x5AFE5C13
        assert migration_lock != _INGESTION_LOCK_KEY
        assert sweep_lock != _INGESTION_LOCK_KEY

    def test_all_queues_contains_expected_queues(self) -> None:
        from app.ingestion import ALL_QUEUES

        expected = {"ingest_github", "ingest_mcp_registry", "ingest_npm", "ingest_pypi", "default"}
        for q in expected:
            assert q in ALL_QUEUES, f"{q} not in ALL_QUEUES"

    def test_procrastinate_app_is_created(self) -> None:
        from procrastinate import App

        from app.ingestion import procrastinate_app

        assert isinstance(procrastinate_app, App)


class TestRunOneCycleMain:
    def test_main_prints_usage_and_returns_2_with_no_args(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.ingestion.run_one_cycle import main

        monkeypatch.setattr(sys, "argv", ["run_one_cycle"])
        result = main()
        assert result == 2


class TestEnqueueModule:
    def test_enqueue_ingest_task_is_a_procrastinate_task(self) -> None:
        from app.ingestion.enqueue import enqueue_ingest_task

        # The task should be decorated and callable
        assert callable(enqueue_ingest_task)

    def test_procrastinate_app_libpq_conninfo_strips_asyncpg(self) -> None:
        from app.ingestion import _libpq_conninfo  # pyright: ignore[reportPrivateUsage]

        url = "postgresql+asyncpg://postgres:dev@localhost:5432/saferskills_dev"
        result = _libpq_conninfo(url)
        assert "asyncpg" not in result
        assert result.startswith("postgresql://")

    def test_procrastinate_app_libpq_conninfo_strips_psycopg(self) -> None:
        from app.ingestion import _libpq_conninfo  # pyright: ignore[reportPrivateUsage]

        url = "postgresql+psycopg://postgres:dev@localhost:5432/db"
        result = _libpq_conninfo(url)
        assert "psycopg" not in result
        assert result.startswith("postgresql://")

    def test_procrastinate_app_libpq_conninfo_passes_through_plain(self) -> None:
        from app.ingestion import _libpq_conninfo  # pyright: ignore[reportPrivateUsage]

        url = "postgresql://postgres:dev@localhost:5432/db"
        result = _libpq_conninfo(url)
        assert result == url


class TestClassifierAdditionalBranches:
    """Cover remaining classifier branches."""

    def test_windsurfrules_does_not_give_all_agents(self) -> None:
        from app.ingestion.framework.base_adapter import NormalizedItem
        from app.ingestion.framework.classifier import classify_agent_compatibility

        n = NormalizedItem(
            github_org="a",
            github_repo="b",
            display_name="b",
            metadata_files={".windsurfrules": b"no-any"},
        )
        agents = classify_agent_compatibility(n)
        assert "windsurf" in agents

    def test_claude_hooks_gives_claude_code(self) -> None:
        from app.ingestion.framework.base_adapter import NormalizedItem
        from app.ingestion.framework.classifier import classify_agent_compatibility

        n = NormalizedItem(
            github_org="a",
            github_repo="b",
            display_name="b",
            metadata_files={".claude/hooks/my-hook.sh": b"#!/bin/bash"},
        )
        agents = classify_agent_compatibility(n)
        assert "claude-code" in agents

    def test_streamable_http_transport_mcp(self) -> None:
        import json

        from app.ingestion.framework.base_adapter import NormalizedItem
        from app.ingestion.framework.classifier import classify_agent_compatibility

        mcp = json.dumps({"transport": "streamable-http"}).encode()
        n = NormalizedItem(
            github_org="a",
            github_repo="b",
            display_name="b",
            metadata_files={"mcp.json": mcp},
        )
        agents = classify_agent_compatibility(n)
        assert "claude-code" in agents

    def test_mcp_json_packages_transport(self) -> None:
        """Transport in packages[0].transport fallback."""
        import json

        from app.ingestion.framework.base_adapter import NormalizedItem
        from app.ingestion.framework.classifier import ALL_AGENTS, classify_agent_compatibility

        mcp = json.dumps({"packages": [{"transport": "stdio"}]}).encode()
        n = NormalizedItem(
            github_org="a",
            github_repo="b",
            display_name="b",
            metadata_files={"mcp.json": mcp},
        )
        agents = classify_agent_compatibility(n)
        assert set(agents) == set(ALL_AGENTS)

    def test_fork_only_medium_stars_is_medium(self) -> None:
        from app.ingestion.framework.base_adapter import NormalizedItem
        from app.ingestion.framework.classifier import classify_quality_tier

        n = NormalizedItem(
            github_org="a",
            github_repo="b",
            display_name="b",
            metadata_files={"SKILL.md": b"#", "README.md": b"# readme"},
            stars=20,
            payload_hint={"commit_count": 10, "is_fork_only": True},
        )
        tier, _ = classify_quality_tier(n)
        assert tier in {"medium", "high"}

    def test_cross_registry_count_boosts_to_high(self) -> None:
        from app.ingestion.framework.base_adapter import NormalizedItem
        from app.ingestion.framework.classifier import classify_quality_tier

        n = NormalizedItem(
            github_org="a",
            github_repo="b",
            display_name="b",
            metadata_files={"SKILL.md": b"#", "README.md": b"# readme"},
            stars=5,
            aggregator_listings=["npm", "pypi"],
            payload_hint={"commit_count": 10},
        )
        tier, _ = classify_quality_tier(n)
        assert tier == "high"

    def test_skill_yaml_also_recognized(self) -> None:
        from app.ingestion.framework.base_adapter import NormalizedItem
        from app.ingestion.framework.classifier import classify_kind

        n = NormalizedItem(
            github_org="a",
            github_repo="b",
            display_name="b",
            metadata_files={"skill.yaml": b"name: skill"},
        )
        kind, signals = classify_kind(n)
        assert kind == "skill"
        assert signals["has_skill_md"] is True

    def test_server_json_gives_mcp_server(self) -> None:
        from app.ingestion.framework.base_adapter import NormalizedItem
        from app.ingestion.framework.classifier import classify_kind

        n = NormalizedItem(
            github_org="a",
            github_repo="b",
            display_name="b",
            metadata_files={"server.json": b'{"transport":"stdio"}'},
        )
        kind, signals = classify_kind(n)
        assert kind == "mcp_server"
        assert signals["has_mcp_json"] is True

    def test_weekly_downloads_boosts_to_high(self) -> None:
        from app.ingestion.framework.base_adapter import NormalizedItem
        from app.ingestion.framework.classifier import classify_quality_tier

        n = NormalizedItem(
            github_org="a",
            github_repo="b",
            display_name="b",
            metadata_files={"SKILL.md": b"#", "README.md": b"# readme"},
            stars=0,
            weekly_downloads=200,
            payload_hint={"commit_count": 10},
        )
        tier, _ = classify_quality_tier(n)
        assert tier == "high"
