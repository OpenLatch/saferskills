# DO NOT EDIT — regenerate via: pnpm run generate (scripts/generate-ingestion-sources.cjs)
"""Generated provider registry — derived from config/sources/*.yaml.

The YAML directory is the single source of truth for ingestion providers. This
module exposes the closed sets consumed across the backend (loader cross-check,
SSRF host allowlist) and is regenerated whenever a YAML is added or changed.
"""

from __future__ import annotations

# Every provider 'name' (the ingestion_events.source / crawler_cursors.source
# closed enum). Includes disabled Phase-B placeholders so the wire enum is stable.
SOURCE_NAMES: frozenset[str] = frozenset(
    {
        "claudeskills_info",
        "clawhub",
        "github_skills",
        "github_topics",
        "glama",
        "mcp_registry",
        "mcp_so",
        "npm",
        "pulsemcp",
        "pypi",
        "skillhub_club",
        "skills_sh",
        "skillsmp",
        "smithery",
    }
)

# Every provider 'registry_id' (defaults to name) — the item_sources.registry_id
# adapter values, before the fixed non-adapter set (user_submission/upload/…).
REGISTRY_IDS: frozenset[str] = frozenset(
    {
        "claudeskills_info",
        "clawhub",
        "github_skills",
        "github_topics",
        "glama",
        "mcp_registry",
        "mcp_so",
        "npm",
        "pulsemcp",
        "pypi",
        "skillhub_club",
        "skills_sh",
        "skillsmp",
        "smithery",
    }
)

# Per-source allowlisted outbound hosts (the YAML 'hosts:' list).
SOURCE_HOSTS: dict[str, frozenset[str]] = {
    "claudeskills_info": frozenset(
        {
            "claudeskills.info",
        }
    ),
    "clawhub": frozenset(
        {
            "clawhub.dev",
        }
    ),
    "github_skills": frozenset(
        {
            "api.github.com",
            "raw.githubusercontent.com",
        }
    ),
    "github_topics": frozenset(
        {
            "api.github.com",
            "raw.githubusercontent.com",
        }
    ),
    "glama": frozenset(
        {
            "glama.ai",
        }
    ),
    "mcp_registry": frozenset(
        {
            "api.github.com",
            "raw.githubusercontent.com",
            "registry.modelcontextprotocol.io",
        }
    ),
    "mcp_so": frozenset(
        {
            "mcp.so",
        }
    ),
    "npm": frozenset(
        {
            "api.npmjs.org",
            "registry.npmjs.com",
            "replicate.npmjs.com",
        }
    ),
    "pulsemcp": frozenset(
        {
            "pulsemcp.com",
        }
    ),
    "pypi": frozenset(
        {
            "pypi.org",
        }
    ),
    "skillhub_club": frozenset(
        {
            "skillhub.club",
        }
    ),
    "skills_sh": frozenset(
        {
            "skills.sh",
        }
    ),
    "skillsmp": frozenset(
        {
            "skillsmp.com",
        }
    ),
    "smithery": frozenset(
        {
            "smithery.ai",
        }
    ),
}

# Union of every provider's hosts — the closed outbound SSRF allowlist.
ALL_HOSTS: frozenset[str] = frozenset(
    {
        "api.github.com",
        "api.npmjs.org",
        "claudeskills.info",
        "clawhub.dev",
        "glama.ai",
        "mcp.so",
        "pulsemcp.com",
        "pypi.org",
        "raw.githubusercontent.com",
        "registry.modelcontextprotocol.io",
        "registry.npmjs.com",
        "replicate.npmjs.com",
        "skillhub.club",
        "skills.sh",
        "skillsmp.com",
        "smithery.ai",
    }
)
