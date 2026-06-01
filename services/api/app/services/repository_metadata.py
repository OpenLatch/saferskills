"""Cached GitHub repository-metadata fetcher.

Mirrors ``app/services/github_stars.py``: anonymous (or ``GITHUB_TOKEN``-auth)
calls to ``api.github.com`` reading public repo facts the item-detail page
surfaces — stars, forks, SPDX license, description, and the latest release tag.
Memoized in-process per repo for ~1h (no Redis per ``.claude/rules/tech-stack.md``).
Any failure/timeout degrades to ``None`` fields.

``api.github.com`` is already on the outbound allowlist
(``.claude/rules/security.md`` § Public-input handling) — no new host. Only
public counts/strings are read; no PII, no request metadata cached.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import cast

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_TTL_SECONDS = 3600.0
_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class RepositoryMetadata:
    """Public GitHub facts mirrored onto a catalog item. All optional."""

    stars: int | None = None
    forks: int | None = None
    license_spdx: str | None = None
    latest_version: str | None = None
    description: str | None = None
    default_branch: str | None = None


# Per-repo timestamped cache: "<org>/<repo>" -> (fetched_at_monotonic, metadata).
_cache: dict[str, tuple[float, RepositoryMetadata]] = {}


def _auth_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SaferSkills-Metadata/0.1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = get_settings().github_token
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def get_repository_metadata(org: str, repo: str) -> RepositoryMetadata:
    """Return public repo metadata, cached ~1h per repo. Fields are ``None`` on failure."""
    key = f"{org}/{repo}"
    now = time.monotonic()
    cached = _cache.get(key)
    if cached is not None and (now - cached[0]) < _TTL_SECONDS:
        return cached[1]

    stars: int | None = None
    forks: int | None = None
    license_spdx: str | None = None
    description: str | None = None
    default_branch: str | None = None
    latest_version: str | None = None

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{org}/{repo}",
                headers=_auth_headers(),
            )
            if resp.status_code == 200:
                body: dict[str, object] = resp.json()
                star_v = body.get("stargazers_count")
                if isinstance(star_v, int):
                    stars = star_v
                fork_v = body.get("forks_count")
                if isinstance(fork_v, int):
                    forks = fork_v
                desc_v = body.get("description")
                if isinstance(desc_v, str):
                    description = desc_v
                branch_v = body.get("default_branch")
                if isinstance(branch_v, str):
                    default_branch = branch_v
                lic = body.get("license")
                if isinstance(lic, dict):
                    spdx = cast("dict[str, object]", lic).get("spdx_id")
                    # GitHub returns "NOASSERTION" for unrecognized licenses.
                    if isinstance(spdx, str) and spdx and spdx != "NOASSERTION":
                        license_spdx = spdx
            else:
                logger.warning("repo metadata: HTTP %s for %s", resp.status_code, key)

            # Latest release tag (separate endpoint; absent → 404, leave None).
            rel = await client.get(
                f"https://api.github.com/repos/{org}/{repo}/releases/latest",
                headers=_auth_headers(),
            )
            if rel.status_code == 200:
                rel_body: dict[str, object] = rel.json()
                tag = rel_body.get("tag_name")
                if isinstance(tag, str) and tag:
                    latest_version = tag
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("repo metadata fetch failed for %s: %s", key, exc)

    meta = RepositoryMetadata(
        stars=stars,
        forks=forks,
        license_spdx=license_spdx,
        latest_version=latest_version,
        description=description,
        default_branch=default_branch,
    )
    _cache[key] = (now, meta)
    return meta


def reset_cache() -> None:
    """Clear the memoized metadata. Used by tests; harmless in production."""
    _cache.clear()
