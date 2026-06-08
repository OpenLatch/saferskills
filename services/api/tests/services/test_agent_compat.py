"""Tests for the deterministic agent-compatibility mapping.

Regression for the install-CLI mismatch: the `skill` kind must list every agent
that natively loads a `skills/` directory (Claude Code + OpenClaw, plus Codex,
Copilot, Gemini — widened in migration 0017), so `saferskills install <skill>`
offers those agents instead of hiding them.
"""

from __future__ import annotations

from app.services.agent_compat import ALL_AGENTS, agent_compatibility_for


def test_skill_includes_skill_capable_agents() -> None:
    compat = agent_compatibility_for("skill")
    for agent in ("claude-code", "codex", "copilot", "gemini", "openclaw"):
        assert agent in compat, agent
    # Rules-only / MCP-transport editors are NOT skill-capable.
    for agent in ("cursor", "windsurf", "cline"):
        assert agent not in compat, agent


def test_mcp_server_is_every_agent() -> None:
    assert set(agent_compatibility_for("mcp_server")) == set(ALL_AGENTS)


def test_plugin_and_hook_stay_claude_only() -> None:
    assert agent_compatibility_for("plugin") == ["claude-code", "openclaw"]
    assert agent_compatibility_for("hook") == ["claude-code", "openclaw"]


def test_rules_targets_rule_editors() -> None:
    assert agent_compatibility_for("rules") == ["cursor", "windsurf", "cline", "copilot"]


def test_unknown_kind_is_empty() -> None:
    assert agent_compatibility_for("nonexistent") == []
