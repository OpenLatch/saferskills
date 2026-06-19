"""Tests for the deterministic agent-compatibility mapping.

Regression for the install-CLI mismatch: the `skill` kind must list EVERY agent,
because the install CLI's general renderer (I-6.5 plan 02) now deposits a native
form of any skill for all eight agents — verbatim SKILL.md for the skills-dir
agents, a `.mdc`/rules `.md` for the rules-dir agents (Cursor/Windsurf/Cline), and
a shared AGENTS.md/GEMINI.md marker block for Codex/Copilot/Gemini (widened from
the 5-agent set in migration 0024). So `saferskills install <skill>` reaches every
detected agent instead of hiding the rules-only editors.
"""

from __future__ import annotations

from app.services.agent_compat import ALL_AGENTS, agent_compatibility_for


def test_skill_includes_all_agents() -> None:
    compat = agent_compatibility_for("skill")
    # Every agent is now skill-capable via the plan-02 renderer.
    assert set(compat) == set(ALL_AGENTS)
    # The rules-only editors are now included (previously excluded).
    for agent in ("cursor", "windsurf", "cline"):
        assert agent in compat, agent


def test_mcp_server_is_every_agent() -> None:
    assert set(agent_compatibility_for("mcp_server")) == set(ALL_AGENTS)


def test_plugin_and_hook_stay_claude_only() -> None:
    assert agent_compatibility_for("plugin") == ["claude-code", "openclaw"]
    assert agent_compatibility_for("hook") == ["claude-code", "openclaw"]


def test_rules_targets_rule_editors() -> None:
    assert agent_compatibility_for("rules") == ["cursor", "windsurf", "cline", "copilot"]


def test_unknown_kind_is_empty() -> None:
    assert agent_compatibility_for("nonexistent") == []
