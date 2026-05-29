"""Deterministic agent-compatibility mapping.

`agent_compatibility` on a `catalog_item` is the closed-enum list of agent
platforms an artifact can run on. At W2 there is no per-artifact manifest parse
yet, so the value is derived **deterministically from the artifact `kind`** — a
documented, reproducible default rather than an opinion. The mapping is the
public methodology contract (see ``docs/methodology.md`` § Agent compatibility);
I-04 ingestion adapters will refine it with real manifest signals (declared
`engines` / `agents` fields, MCP transport, editor-rule frontmatter).

The same CASE-on-kind logic is mirrored in the Alembic backfill
(``2026_05_29_0003_add_agent_compatibility``) so existing rows match new ones.
Keep the two in sync — when this mapping changes, ship a new backfill migration.
"""

from __future__ import annotations

# Closed enum — mirrors schemas/catalog-item.schema.json::agentCompatibility.
ALL_AGENTS: tuple[str, ...] = (
    "claude-code",
    "cursor",
    "codex",
    "copilot",
    "windsurf",
    "cline",
    "gemini",
    "openclaw",
)

# kind → the agents that can consume that artifact kind.
#   mcp_server : MCP is a cross-agent transport standard → every agent.
#   skill      : Claude Skills format → Claude Code + the Claude-compatible OpenClaw.
#   plugin     : Claude Code plugin packaging → Claude Code (+ OpenClaw).
#   hook       : Claude Code lifecycle hooks → Claude Code (+ OpenClaw).
#   rules      : editor rule files → the rule-consuming editors.
_KIND_TO_AGENTS: dict[str, tuple[str, ...]] = {
    "mcp_server": ALL_AGENTS,
    "skill": ("claude-code", "openclaw"),
    "plugin": ("claude-code", "openclaw"),
    "hook": ("claude-code", "openclaw"),
    "rules": ("cursor", "windsurf", "cline", "copilot"),
}


def agent_compatibility_for(kind: str) -> list[str]:
    """Return the deterministic agent-compatibility list for an artifact kind.

    Unknown kinds fall back to the empty list (no claim is the honest default).
    """
    return list(_KIND_TO_AGENTS.get(kind, ()))
