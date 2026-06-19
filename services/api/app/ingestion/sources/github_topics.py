"""GitHub topic-search + code-search discovery adapter.

Topics indexed: claude-skills, anthropic-skills, agent-skills, mcp-server.
The GitHub Search API caps at 1,000 results/query; we shard by star-count ranges
declared in the YAML `discovery.star_shards` to keep each query under the cap.

When `get_settings().ingestion_github_code_search_enabled` is True a second pass
hits `https://api.github.com/search/code` for the queries in
`discovery.code_search_queries`, deduplicating on full_name across both passes.

Cadence: daily 01:00 UTC (discovery.cadence_cron in YAML).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
from collections.abc import AsyncIterator
from typing import Any, cast

import structlog

from app.ingestion.config.loader import SourceConfig
from app.ingestion.framework.base_adapter import (
    NormalizedItem,
    RawItem,
    register_adapter,
)
from app.ingestion.framework.registry_adapter import RegistryAdapter

# Type alias for JSON payloads from the GitHub API
_JsonDict = dict[str, Any]

logger = structlog.get_logger(__name__)


@register_adapter("github_topics")
class GithubTopicsAdapter(RegistryAdapter):
    """Discover repos via GitHub topic-search (+ optional code-search)."""

    def __init__(self, config: SourceConfig) -> None:
        super().__init__(config)

    async def list_items(self, client: Any) -> AsyncIterator[RawItem]:
        """Yield one RawItem per repo discovered across all topic shards.

        Deduplicates on full_name so each repo is yielded at most once even
        when it appears in multiple topic x shard queries.
        """
        from app.core.config import get_settings

        seen: set[str] = set()

        topics: list[str] = self.config.discovery.get("topics", [])
        star_shards: list[str] = self.config.discovery.get("star_shards", [])

        for topic in topics:
            for shard in star_shards:
                q = f"topic:{topic} {shard}"
                async for raw in self._iter_repo_search(client, q, seen):
                    yield raw

        if get_settings().ingestion_github_code_search_enabled:
            queries: list[str] = self.config.discovery.get("code_search_queries", [])
            for q in queries:
                async for raw in self._iter_code_search(client, q, seen):
                    yield raw

    async def _iter_repo_search(
        self,
        client: Any,
        q: str,
        seen: set[str],
    ) -> AsyncIterator[RawItem]:
        """Paginate the repository search endpoint for one query string."""
        page = 1
        while page <= 10:  # 100 items x 10 pages = 1,000 max per Search API
            r = await client.get(
                "https://api.github.com/search/repositories",
                params={
                    "q": q,
                    "per_page": 100,
                    "page": page,
                    "sort": "stars",
                    "order": "desc",
                },
            )
            if r.status_code == 304:
                yield RawItem(
                    source_id=f"topics/q:{q}/page:{page}",
                    raw_body_bytes=b"",
                    raw_body_hash=hashlib.sha256(b"").hexdigest(),
                    http_status=304,
                    etag=r.headers.get("etag"),
                    from_cache=True,
                    fetch_tier=1,
                )
                page += 1
                continue
            if r.status_code != 200:
                yield RawItem(
                    source_id=f"topics/q:{q}/page:{page}",
                    raw_body_bytes=r.content,
                    raw_body_hash=hashlib.sha256(r.content).hexdigest(),
                    http_status=r.status_code,
                    error_reason=(
                        "rate_limit"
                        if r.status_code in (429, 403)
                        else "http_5xx"
                        if r.status_code >= 500
                        else "other"
                    ),
                    fetch_tier=1,
                )
                break
            data: _JsonDict = r.json()
            items: list[_JsonDict] = list(data.get("items") or [])
            if not items:
                break
            for item in items:
                full_name: str = str(item.get("full_name") or "")
                if full_name in seen:
                    continue
                seen.add(full_name)
                body = json.dumps(item, separators=(",", ":"), sort_keys=True).encode()
                yield RawItem(
                    source_id=full_name,
                    raw_body_bytes=body,
                    raw_body_hash=hashlib.sha256(body).hexdigest(),
                    http_status=200,
                    etag=r.headers.get("etag"),
                    fetched_at=dt.datetime.now(tz=dt.UTC).isoformat(),
                    from_cache=False,
                    fetch_tier=1,
                    payload_hint=item,
                )
            total_count: int = int(data.get("total_count") or 0)
            if total_count <= page * 100 or len(items) < 100:
                break
            page += 1
            await asyncio.sleep(0)  # yield control to the event loop

    async def _iter_code_search(
        self,
        client: Any,
        q: str,
        seen: set[str],
    ) -> AsyncIterator[RawItem]:
        """Paginate the code-search endpoint and surface distinct repos.

        The code-search API returns file hits; we de-key them to the repo level
        (full_name) to avoid creating a catalog item per matched file. Repos
        already emitted by the topic-search pass are skipped via `seen`.
        """
        page = 1
        while page <= 10:
            r = await client.get(
                "https://api.github.com/search/code",
                params={"q": q, "per_page": 100, "page": page},
                headers={"Accept": "application/vnd.github.text-match+json"},
            )
            if r.status_code == 304:
                yield RawItem(
                    source_id=f"code_search/q:{q}/page:{page}",
                    raw_body_bytes=b"",
                    raw_body_hash=hashlib.sha256(b"").hexdigest(),
                    http_status=304,
                    etag=r.headers.get("etag"),
                    from_cache=True,
                    fetch_tier=1,
                )
                page += 1
                continue
            if r.status_code != 200:
                yield RawItem(
                    source_id=f"code_search/q:{q}/page:{page}",
                    raw_body_bytes=r.content,
                    raw_body_hash=hashlib.sha256(r.content).hexdigest(),
                    http_status=r.status_code,
                    error_reason=(
                        "rate_limit"
                        if r.status_code in (429, 403)
                        else "http_5xx"
                        if r.status_code >= 500
                        else "other"
                    ),
                    fetch_tier=1,
                )
                break
            data2: _JsonDict = r.json()
            items2: list[_JsonDict] = list(data2.get("items") or [])
            if not items2:
                break
            for item in items2:
                repo: _JsonDict = dict(item.get("repository") or {})
                full_name = str(repo.get("full_name") or "")
                if not full_name or full_name in seen:
                    continue
                seen.add(full_name)
                body = json.dumps(repo, separators=(",", ":"), sort_keys=True).encode()
                yield RawItem(
                    source_id=full_name,
                    raw_body_bytes=body,
                    raw_body_hash=hashlib.sha256(body).hexdigest(),
                    http_status=200,
                    etag=r.headers.get("etag"),
                    fetched_at=dt.datetime.now(tz=dt.UTC).isoformat(),
                    from_cache=False,
                    fetch_tier=1,
                    payload_hint=repo,
                )
            total_count2: int = int(data2.get("total_count") or 0)
            if total_count2 <= page * 100 or len(items2) < 100:
                break
            page += 1
            await asyncio.sleep(0)

    def normalize(self, raw: RawItem) -> NormalizedItem | None:
        """Map a GitHub repo JSON payload to the canonical NormalizedItem shape."""
        if raw.http_status != 200:
            return None
        item: _JsonDict = raw.payload_hint
        if not isinstance(item, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
            return None
        owner_raw: Any = item.get("owner")
        owner_obj: _JsonDict = cast(_JsonDict, owner_raw) if isinstance(owner_raw, dict) else {}
        org: str = str(owner_obj.get("login") or "")
        repo: str = str(item.get("name") or "")
        if not org or not repo:
            return None
        license_raw: Any = item.get("license")
        license_obj: _JsonDict = (
            cast(_JsonDict, license_raw) if isinstance(license_raw, dict) else {}
        )
        license_spdx: str | None = (
            str(license_obj.get("spdx_id")) if license_obj.get("spdx_id") else None
        )
        stars_raw: Any = item.get("stargazers_count")
        stars: int | None = int(stars_raw) if stars_raw is not None else None
        return NormalizedItem(
            github_org=org,
            github_repo=repo,
            display_name=repo,
            description=str(item.get("description") or "")[:280],
            license_spdx=license_spdx,
            github_url=str(item.get("html_url") or "") or None,
            source_url=str(item.get("html_url") or "") or None,
            stars=stars,
            pushed_at=str(item.get("pushed_at") or "") or None,
            default_branch=str(item.get("default_branch") or "") or None,
            repo_archived=bool(item.get("archived", False)),
            metadata_files={},  # populated by enrich()
            aggregator_listings=[self.config.name],
            payload_hint={"commit_count": int(item.get("size") or 0)},
        )

    async def enrich(self, client: Any, normalized: NormalizedItem) -> None:
        """Fetch SKILL.md / mcp.json / README.md into metadata_files (best-effort)."""
        if not normalized.github_org or not normalized.github_repo:
            return
        branch = normalized.default_branch or "main"
        for filename in ("SKILL.md", "mcp.json", "README.md"):
            url = (
                f"https://raw.githubusercontent.com/"
                f"{normalized.github_org}/{normalized.github_repo}/{branch}/{filename}"
            )
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    normalized.metadata_files[filename] = r.content
            except Exception:
                pass
