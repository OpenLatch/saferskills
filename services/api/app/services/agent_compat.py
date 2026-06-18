"""Deterministic agent-compatibility mapping.

`agent_compatibility` on a `catalog_item` is the closed-enum list of agent
platforms an artifact can run on. At W2 there is no per-artifact manifest parse
yet, so the value is derived **deterministically from the artifact `kind`** — a
documented, reproducible default rather than an opinion. The mapping is the
public methodology contract (see ``docs/methodology.md`` § Agent compatibility);
I-04 ingestion adapters will refine it with real manifest signals (declared
`engines` / `agents` fields, MCP transport, editor-rule frontmatter).

The same CASE-on-kind logic is mirrored in the Alembic backfill
(``2026_05_29_0003_add_agent_compatibility``, with the `skill` set widened to the
5-agent Codex set by ``2026_06_08_0017_skill_compat_codex`` and then to ALL eight
agents by ``2026_06_18_0024_skill_compat_all_agents``) so existing rows match new
ones. Keep the two in sync — when this mapping changes, ship a new backfill
migration.
"""

from __future__ import annotations

from typing import Literal, get_args

# Closed enum — mirrors schemas/catalog-item.schema.json::agentCompatibility +
# app/models/install_event.py::AGENT_VALUES (the native `agent` PG enum). The
# canonical agent ids the install CLI's `--to` flag uses (D-05-14); the legacy
# `codex-cli`/`gemini-cli` ids are reconciled to `codex`/`gemini`.
AgentName = Literal[
    "claude-code",
    "cursor",
    "codex",
    "copilot",
    "windsurf",
    "cline",
    "gemini",
    "openclaw",
]

# Runtime tuple derived from the Literal so the two never drift (order preserved).
ALL_AGENTS: tuple[str, ...] = get_args(AgentName)

# kind → the agents that can consume that artifact kind.
#   mcp_server : MCP is a cross-agent transport standard → every agent.
#   skill      : the Claude Skills (SKILL.md) format → now EVERY agent. The
#                install CLI's general renderer (`cli/src/agents/writers/render.rs`,
#                plan 02) deposits a native form for every agent: verbatim SKILL.md
#                for the skills-dir agents (Claude Code, OpenClaw, Codex, Copilot,
#                Gemini), a `.mdc`/rules `.md` for the rules-dir agents (Cursor,
#                Windsurf, Cline), and a shared AGENTS.md/GEMINI.md marker block for
#                Codex/Copilot/Gemini. So the catalog must assert skill on all eight
#                (widened from the 5-agent set in migration 0017_skill_compat_codex
#                by 0024_skill_compat_all_agents).
#   plugin     : Claude Code plugin packaging → Claude Code (+ OpenClaw).
#   hook       : Claude Code lifecycle hooks → Claude Code (+ OpenClaw).
#   rules      : editor rule files → the rule-consuming editors.
_KIND_TO_AGENTS: dict[str, tuple[str, ...]] = {
    "mcp_server": ALL_AGENTS,
    "skill": ALL_AGENTS,
    "plugin": ("claude-code", "openclaw"),
    "hook": ("claude-code", "openclaw"),
    "rules": ("cursor", "windsurf", "cline", "copilot"),
}


def agent_compatibility_for(kind: str) -> list[str]:
    """Return the deterministic agent-compatibility list for an artifact kind.

    Unknown kinds fall back to the empty list (no claim is the honest default).
    """
    return list(_KIND_TO_AGENTS.get(kind, ()))
