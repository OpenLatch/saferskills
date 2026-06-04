"""Deterministic multi-signal classifier — kind + quality_tier + agent_compatibility.

No LLM (methodology over opinion). Re-runnable via the Phase C admin CLI. The
agent heuristic writes the EXISTING `agent_compatibility` column (migration 0003),
whose closed enum is the hyphenated 8-agent set below — NOT the plan's draft
`claude_code`/`all`/`mcp_universal` tokens, which are not catalog-item enum values.
"""

from __future__ import annotations

import json
from typing import Any

from app.ingestion.framework.base_adapter import NormalizedItem

# The catalog-item agentCompatibility closed enum — single source of truth lives
# in app.services.agent_compat (mirrored from schemas/catalog-item.schema.json).
# Reused here to prevent drift between the two.
from app.services.agent_compat import ALL_AGENTS

CLASSIFIER_VERSION = "v1"


def classify_kind(n: NormalizedItem) -> tuple[str, dict[str, Any]]:
    """Return (kind, kind_signals).

    SKILL.md → 'skill'; mcp.json/server.json (or an mcp-server-* name) → 'mcp_server';
    .cursorrules-only → 'rules'; hooks/plugins fold to 'skill' (deferred to V1.2);
    default 'skill'.
    """
    files = n.metadata_files or {}
    has_skill_md = "SKILL.md" in files or "skill.yaml" in files
    has_mcp_json = "mcp.json" in files or "server.json" in files
    package_name_matches_mcp = bool(
        n.github_repo
        and (n.github_repo.startswith("mcp-server-") or n.github_repo.startswith("claude-skill-"))
    )
    has_cursorrules = ".cursorrules" in files
    has_claude_hooks = any(p.startswith(".claude/hooks/") for p in files)

    if has_mcp_json or package_name_matches_mcp:
        kind = "mcp_server"
    elif has_skill_md:
        kind = "skill"
    elif has_cursorrules:
        kind = "rules"
    else:
        kind = "skill"

    signals = {
        "has_skill_md": has_skill_md,
        "has_mcp_json": has_mcp_json,
        "package_name_matches_mcp_pattern": package_name_matches_mcp,
        "has_cursorrules": has_cursorrules,
        "has_claude_hooks": has_claude_hooks,
        "classified_as": kind,
        "classifier_version": CLASSIFIER_VERSION,
    }
    return kind, signals


def classify_quality_tier(n: NormalizedItem) -> tuple[str, dict[str, Any]]:
    """Return (quality_tier, quality_signals). See D-04-19 heuristic."""
    files = n.metadata_files or {}
    has_readme = any(f in files for f in ("README.md", "README", "readme.md"))
    has_manifest = any(
        f in files
        for f in ("SKILL.md", "mcp.json", "server.json", "package.json", "pyproject.toml")
    )
    hint = n.payload_hint or {}
    commit_count = int(hint.get("commit_count", 0) or 0)
    is_fork_only = bool(hint.get("is_fork_only", False))
    is_empty = not has_readme and not has_manifest and commit_count == 0
    stars = n.stars or 0
    weekly_downloads = n.weekly_downloads or 0
    cross_registry_count = len(n.aggregator_listings or [])

    signals = {
        "has_readme": has_readme,
        "has_manifest": has_manifest,
        "commit_count": commit_count,
        "is_fork_only": is_fork_only,
        "is_empty": is_empty,
        "stars": stars,
        "weekly_downloads": weekly_downloads,
        "cross_registry_count": cross_registry_count,
        "classifier_version": CLASSIFIER_VERSION,
    }

    if is_empty:
        return "empty", signals
    if is_fork_only and stars < 10 and not has_manifest:
        return "low", signals
    if commit_count < 3 and stars < 5:
        return "low", signals
    if has_readme and has_manifest and commit_count >= 5:
        if stars >= 50 or weekly_downloads > 100 or cross_registry_count >= 2:
            return "high", signals
        return "medium", signals
    return "medium", signals


def classify_agent_compatibility(n: NormalizedItem) -> list[str]:
    """Return a sorted list of agent slugs from the catalog-item agent enum."""
    files = n.metadata_files or {}
    agents: set[str] = set()

    if "SKILL.md" in files or "skill.yaml" in files:
        agents.add("claude-code")
    if any(p.startswith(".claude/hooks/") for p in files):
        agents.add("claude-code")
    if ".cursorrules" in files:
        agents.add("cursor")
    if ".windsurfrules" in files:
        agents.add("windsurf")

    mcp_manifest = files.get("mcp.json") or files.get("server.json")
    if mcp_manifest:
        transport: str | None = None
        try:
            doc = json.loads(mcp_manifest.decode("utf-8"))
            transport = doc.get("transport")
            if transport is None and isinstance(doc.get("packages"), list) and doc["packages"]:
                transport = doc["packages"][0].get("transport")
        except ValueError, AttributeError, KeyError, TypeError:
            transport = None
        if transport == "stdio":
            agents.update(ALL_AGENTS)  # universal stdio MCP
        elif transport in {"sse", "streamable-http"}:
            agents.add("claude-code")
        else:
            agents.update(ALL_AGENTS)  # unknown transport on a manifest → assume broad

    if not agents:
        # Honor the adapter's kind hint (e.g. mcp_registry/npm declare mcp_server)
        # when no file signals are present; fall back to the file-based classifier.
        kind = n.kind or classify_kind(n)[0]
        if kind == "mcp_server":
            agents.update(ALL_AGENTS)
        else:
            agents.add("claude-code")

    return sorted(agents)


def classify_all(n: NormalizedItem) -> tuple[str, dict[str, Any], str, dict[str, Any], list[str]]:
    """Convenience: run all three classifiers in one call."""
    kind, kind_signals = classify_kind(n)
    quality_tier, quality_signals = classify_quality_tier(n)
    agents = classify_agent_compatibility(n)
    return kind, kind_signals, quality_tier, quality_signals, agents
