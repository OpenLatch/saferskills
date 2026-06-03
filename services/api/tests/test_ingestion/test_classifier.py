"""Tests for app.ingestion.framework.classifier — kind, quality_tier, agent_compatibility."""

from __future__ import annotations

import json

from app.ingestion.framework.base_adapter import NormalizedItem
from app.ingestion.framework.classifier import (
    ALL_AGENTS,
    classify_agent_compatibility,
    classify_all,
    classify_kind,
    classify_quality_tier,
)
from tests.test_ingestion.conftest import make_normalized

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SKILL_MD = b"# My Skill\n\nDoes useful things."
_MCP_JSON_STDIO = json.dumps({"transport": "stdio", "name": "my-mcp"}).encode()
_MCP_JSON_SSE = json.dumps({"transport": "sse"}).encode()
_MCP_JSON_NO_TRANSPORT = json.dumps({"name": "some-mcp"}).encode()


def _mcp_server_item(
    transport: str | None = "stdio",
    repo: str = "mcp-server-test",
    extra_files: dict[str, bytes] | None = None,
) -> NormalizedItem:
    mcp_doc: dict[str, object] = {"name": repo}
    if transport is not None:
        mcp_doc["transport"] = transport
    files = {"mcp.json": json.dumps(mcp_doc).encode()}
    if extra_files:
        files.update(extra_files)
    return make_normalized(github_repo=repo, metadata_files=files)


def _skill_item(
    stars: int = 5,
    commit_count: int = 3,
    has_readme: bool = True,
) -> NormalizedItem:
    files: dict[str, bytes] = {"SKILL.md": _SKILL_MD}
    if has_readme:
        files["README.md"] = b"# readme"
    return make_normalized(
        metadata_files=files,
        stars=stars,
        payload_hint={"commit_count": commit_count},
    )


def _rules_item() -> NormalizedItem:
    return make_normalized(metadata_files={".cursorrules": b"no var declarations"})


def _empty_item() -> NormalizedItem:
    return make_normalized(metadata_files={}, stars=0, payload_hint={"commit_count": 0})


def _high_quality_item() -> NormalizedItem:
    return make_normalized(
        metadata_files={"SKILL.md": _SKILL_MD, "README.md": b"# readme"},
        stars=100,
        payload_hint={"commit_count": 20},
    )


def _low_quality_item() -> NormalizedItem:  # pyright: ignore[reportUnusedFunction]
    return make_normalized(
        metadata_files={},
        stars=0,
        payload_hint={"commit_count": 1, "is_fork_only": True},
    )


# ---------------------------------------------------------------------------
# classify_kind
# ---------------------------------------------------------------------------


class TestClassifyKind:
    def test_skill_md_gives_skill(self) -> None:
        n = make_normalized(metadata_files={"SKILL.md": _SKILL_MD})
        kind, signals = classify_kind(n)
        assert kind == "skill"
        assert signals["has_skill_md"] is True

    def test_mcp_json_gives_mcp_server(self) -> None:
        n = make_normalized(metadata_files={"mcp.json": _MCP_JSON_STDIO})
        kind, signals = classify_kind(n)
        assert kind == "mcp_server"
        assert signals["has_mcp_json"] is True

    def test_repo_name_mcp_server_prefix_gives_mcp_server(self) -> None:
        n = make_normalized(github_repo="mcp-server-cool", metadata_files={})
        kind, _ = classify_kind(n)
        assert kind == "mcp_server"

    def test_cursorrules_gives_rules(self) -> None:
        n = _rules_item()
        kind, signals = classify_kind(n)
        assert kind == "rules"
        assert signals["has_cursorrules"] is True

    def test_empty_item_defaults_to_skill(self) -> None:
        n = _empty_item()
        kind, _ = classify_kind(n)
        assert kind == "skill"

    def test_mcp_overrides_skill_md(self) -> None:
        """mcp.json takes priority over SKILL.md."""
        n = make_normalized(metadata_files={"mcp.json": _MCP_JSON_STDIO, "SKILL.md": _SKILL_MD})
        kind, _ = classify_kind(n)
        assert kind == "mcp_server"


# ---------------------------------------------------------------------------
# classify_quality_tier
# ---------------------------------------------------------------------------


class TestClassifyQualityTier:
    def test_empty_item_is_empty_tier(self) -> None:
        n = _empty_item()
        tier, signals = classify_quality_tier(n)
        assert tier == "empty"
        assert signals["is_empty"] is True

    def test_fork_only_low_stars_no_manifest_is_low(self) -> None:
        n = make_normalized(
            metadata_files={},
            stars=0,
            payload_hint={"commit_count": 5, "is_fork_only": True},
        )
        tier, _ = classify_quality_tier(n)
        assert tier == "low"

    def test_low_commits_low_stars_is_low(self) -> None:
        n = make_normalized(
            metadata_files={"README.md": b"# hi"},
            stars=2,
            payload_hint={"commit_count": 1},
        )
        tier, _ = classify_quality_tier(n)
        assert tier == "low"

    def test_high_quality_item_is_high(self) -> None:
        n = _high_quality_item()
        tier, signals = classify_quality_tier(n)
        assert tier == "high"
        assert signals["stars"] == 100

    def test_medium_quality_baseline(self) -> None:
        n = _skill_item(stars=10, commit_count=10, has_readme=True)
        tier, _ = classify_quality_tier(n)
        assert tier in {"medium", "high"}

    def test_classifier_version_in_signals(self) -> None:
        n = _skill_item()
        _, signals = classify_quality_tier(n)
        assert "classifier_version" in signals


# ---------------------------------------------------------------------------
# classify_agent_compatibility
# ---------------------------------------------------------------------------


class TestClassifyAgentCompatibility:
    def test_all_agents_are_valid_enum_values(self) -> None:
        assert set(ALL_AGENTS) == {
            "claude-code",
            "cursor",
            "codex",
            "copilot",
            "windsurf",
            "cline",
            "gemini",
            "openclaw",
        }

    def test_skill_md_gives_claude_code(self) -> None:
        n = make_normalized(metadata_files={"SKILL.md": _SKILL_MD})
        agents = classify_agent_compatibility(n)
        assert "claude-code" in agents
        assert set(agents).issubset(set(ALL_AGENTS))

    def test_stdio_mcp_gives_all_agents(self) -> None:
        n = _mcp_server_item(transport="stdio")
        agents = classify_agent_compatibility(n)
        assert set(agents) == set(ALL_AGENTS)

    def test_sse_mcp_gives_claude_code(self) -> None:
        n = _mcp_server_item(transport="sse")
        agents = classify_agent_compatibility(n)
        assert "claude-code" in agents
        assert set(agents).issubset(set(ALL_AGENTS))

    def test_cursorrules_adds_cursor(self) -> None:
        n = _rules_item()
        agents = classify_agent_compatibility(n)
        assert "cursor" in agents

    def test_windsurfrules_adds_windsurf(self) -> None:
        n = make_normalized(metadata_files={".windsurfrules": b"no-any"})
        agents = classify_agent_compatibility(n)
        assert "windsurf" in agents

    def test_empty_item_defaults_to_claude_code(self) -> None:
        n = _empty_item()
        agents = classify_agent_compatibility(n)
        assert "claude-code" in agents
        assert set(agents).issubset(set(ALL_AGENTS))

    def test_mcp_server_kind_no_manifest_gets_all(self) -> None:
        """mcp_server without a mcp.json manifest defaults to all agents."""
        n = make_normalized(github_repo="mcp-server-x", metadata_files={})
        agents = classify_agent_compatibility(n)
        assert set(agents) == set(ALL_AGENTS)

    def test_result_is_sorted(self) -> None:
        n = _mcp_server_item(transport="stdio")
        agents = classify_agent_compatibility(n)
        assert agents == sorted(agents)


# ---------------------------------------------------------------------------
# classify_all convenience wrapper
# ---------------------------------------------------------------------------


class TestClassifyAll:
    def test_returns_five_tuple(self) -> None:
        n = _skill_item()
        result = classify_all(n)
        assert len(result) == 5

    def test_consistency_with_individual_classifiers(self) -> None:
        n = _mcp_server_item(transport="stdio")
        kind_all, _ks_all, tier_all, _qs_all, agents_all = classify_all(n)
        kind, _ks = classify_kind(n)
        tier, _qs = classify_quality_tier(n)
        agents = classify_agent_compatibility(n)
        assert kind_all == kind
        assert tier_all == tier
        assert agents_all == agents
