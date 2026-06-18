"""Shared GitHub repo-facts + manifest enrichment.

Factored out of `mcp_registry.enrich` so every adapter whose listing feed carries
no repo signals (the aggregator scrapers, the MCP registry) can populate the
signals the quality classifier needs — without each re-implementing the same two
fetches. An item lacking these signals classifies `quality_tier='empty'` and is
hidden by the default catalog gate (`quality_tier IN ('high','medium')`).

`enrich_repo_facts(client, normalized)`:
  1. `GET api.github.com/repos/{org}/{repo}` → stars, `commit_count` proxy (repo
     `size`), default branch, pushed_at, archived, license.
  2. `GET raw.githubusercontent.com/{org}/{repo}/{branch}/{file}` for each manifest
     in `manifest_files` → `metadata_files` bytes.

Both passes require `api.github.com` + `raw.githubusercontent.com` in the adapter's
YAML `hosts:` list (the per-adapter SSRF allowlist + the GitHub-App-token hook key
on `api.github.com`). Best-effort: any fetch failure leaves the item as the listing
presented it (still indexable, just lower-tier).
"""

from __future__ import annotations

from typing import Any, cast

import structlog

from app.ingestion.framework.base_adapter import NormalizedItem

logger = structlog.get_logger(__name__)

_GITHUB_URL_PREFIXES = (
    "https://github.com/",
    "http://github.com/",
    "git+https://github.com/",
    "git://github.com/",
    "ssh://git@github.com/",
)


def parse_github_coords(url: str | None) -> tuple[str | None, str | None]:
    """Extract (org, repo) from a GitHub URL, stripping `.git`, fragments, query
    strings, and trailing path segments. Returns (None, None) for non-GitHub URLs."""
    if not url:
        return None, None
    for prefix in _GITHUB_URL_PREFIXES:
        if url.startswith(prefix):
            rest = url[len(prefix) :]
            # Drop fragment (#readme) + query (?tab=...) before splitting the path.
            rest = rest.split("#", 1)[0].split("?", 1)[0]
            parts = rest.rstrip("/").split("/")
            if len(parts) >= 2 and parts[0] and parts[1]:
                return parts[0], parts[1].removesuffix(".git")
    return None, None


# Manifests the quality classifier + agent-compat classifier look for. Covers the
# skill, MCP, and package shapes the aggregators surface.
DEFAULT_MANIFEST_FILES: tuple[str, ...] = (
    "SKILL.md",
    "mcp.json",
    "server.json",
    "package.json",
    "pyproject.toml",
    "README.md",
)


async def enrich_repo_facts(
    client: Any,
    normalized: NormalizedItem,
    *,
    manifest_files: tuple[str, ...] = DEFAULT_MANIFEST_FILES,
) -> None:
    """Populate `normalized` with GitHub repo facts + manifest bytes (best-effort).

    No-op when the item has no GitHub coordinates (a repo-less aggregator listing —
    those fall through to the fuzzy queue and stay low-tier until matched)."""
    org, repo = normalized.github_org, normalized.github_repo
    if not org or not repo:
        return

    try:
        r = await client.get(f"https://api.github.com/repos/{org}/{repo}")
        if r.status_code == 200:
            body: dict[str, Any] = r.json()
            stars = body.get("stargazers_count")
            if isinstance(stars, int):
                normalized.stars = stars
            # GitHub repo `size` (KB) is the commit-count proxy github_topics uses —
            # a non-zero size lifts an item out of `empty`.
            size = body.get("size")
            if isinstance(size, int):
                normalized.payload_hint = {**normalized.payload_hint, "commit_count": size}
            branch = body.get("default_branch")
            if isinstance(branch, str) and branch:
                normalized.default_branch = branch
            pushed = body.get("pushed_at")
            if isinstance(pushed, str) and pushed:
                normalized.pushed_at = pushed
            if body.get("archived"):
                normalized.repo_archived = True
            lic = body.get("license")
            if isinstance(lic, dict):
                spdx = cast("dict[str, Any]", lic).get("spdx_id")
                # GitHub returns "NOASSERTION" for unrecognized licenses.
                if isinstance(spdx, str) and spdx and spdx != "NOASSERTION":
                    normalized.license_spdx = spdx
    except Exception:
        logger.debug("github_enrich.repo_meta_failed", org=org, repo=repo)

    branch = normalized.default_branch or "main"
    for filename in manifest_files:
        url = f"https://raw.githubusercontent.com/{org}/{repo}/{branch}/{filename}"
        try:
            r = await client.get(url)
            if r.status_code == 200:
                normalized.metadata_files[filename] = r.content
        except Exception:
            logger.debug("github_enrich.file_failed", org=org, repo=repo, file=filename)
