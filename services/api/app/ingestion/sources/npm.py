"""npm registry search-API adapter.

Enumerate-then-fetch (mirrors the pypi adapter): for each configured search query,
page the npm registry search API (`registry.npmjs.org/-/v1/search`) and keep package
names that actually start with one of `discovery.name_prefixes` (the search is fuzzy —
`text=mcp-server-` returns 300k+ loosely-related hits, relevance-ranked, so the real
prefix matches cluster near the top and a bounded page walk captures them). Then GET
each candidate's packument (`registry.npmjs.org/<name>`) and yield it; the packument
has the SAME `dist-tags`/`versions`/`repository`/`license` shape the retired
`_changes?include_docs=true` `doc` had, so `normalize()` is reused unchanged.

This replaces the dead CouchDB replication feed (`replicate.npmjs.com/_changes`), which
npm deprecated — it returned `last_seq=0` / 0 items / a hard HTTP 400 every cycle.

Cursor: stateless per-cycle re-scan (these niche prefixes yield hundreds of candidates,
not millions), relying on Hishel conditional GET + content-hash no-op upsert to stay
cheap rather than a per-query offset cursor. The `completed`-gated terminal `write_cursor`
still resets the failure streak / stamps `last_successful_cycle_at` on a clean cycle.

Cadence: hourly at :00 UTC.
"""

from __future__ import annotations

import hashlib
import re
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

logger = structlog.get_logger(__name__)

_GITHUB_REPO_RE = re.compile(r"(?:git\+)?https://github\.com/([^/]+)/([^/\s\.]+?)(?:\.git)?$")
_GITHUB_SSH_RE = re.compile(r"git\+ssh://git@github\.com/([^/]+)/([^/\s\.]+?)(?:\.git)?$")

# npm's `-/v1/search` caps `size` at 250 and deep pagination at `from` ≈ 10k. The
# results are relevance-ranked, so the packages whose name actually starts with a
# target prefix cluster in the first pages — a small page cap captures them while
# bounding the per-cycle enumeration cost (the global cap is `max_items_per_cycle`).
_SEARCH_PAGE_SIZE = 250
_MAX_SEARCH_PAGES_PER_QUERY = 8


def _parse_github_coords(repo_url: str) -> tuple[str | None, str | None]:
    for pattern in (_GITHUB_REPO_RE, _GITHUB_SSH_RE):
        m = pattern.match(repo_url.strip())
        if m:
            return m.group(1), m.group(2)
    return None, None


def _packument_url(registry_base: str, name: str) -> str:
    """Packument URL. Scoped names (`@scope/pkg`) encode the `/` as `%2F` per the npm
    registry convention; unscoped names have no `/` so this is a no-op."""
    return f"{registry_base.rstrip('/')}/{name.replace('/', '%2F')}"


@register_adapter("npm")
class NpmAdapter(RegistryAdapter):
    """Enumerate MCP/skill packages via the npm registry search API, then fetch each
    packument."""

    def __init__(self, config: SourceConfig) -> None:
        super().__init__(config)

    async def _enumerate_candidates(
        self, client: Any, *, search_url: str, queries: list[str], name_prefixes: list[str]
    ) -> tuple[list[str], bool]:
        """Page the search API for every query, returning `(candidates, any_search_ok)`.

        `candidates` is the de-duplicated package names that actually start with a target
        prefix (search is fuzzy). `any_search_ok` is True iff at least one search request
        returned 200/304 — the gate that distinguishes a genuine empty result (a real
        response with no matches → success) from a total registry failure (every query
        429'd / errored → a failed cycle, never a silent false-green). Best-effort per
        query: a search-page non-200 / error breaks THAT query's pagination and moves
        on — never aborts the whole enumeration."""
        seen: set[str] = set()
        candidates: list[str] = []
        any_ok = False
        for query in queries:
            for page in range(_MAX_SEARCH_PAGES_PER_QUERY):
                try:
                    r = await client.get(
                        search_url,
                        params={
                            "text": query,
                            "size": str(_SEARCH_PAGE_SIZE),
                            "from": str(page * _SEARCH_PAGE_SIZE),
                        },
                    )
                except Exception:
                    logger.warning("npm.search_error", query=query, page=page)
                    break
                if r.status_code not in (200, 304):
                    logger.warning("npm.search_non_200", query=query, status=r.status_code)
                    break
                any_ok = True
                try:
                    data: dict[str, Any] = r.json()
                except Exception:
                    break
                objects = cast("list[Any]", data.get("objects") or [])
                for obj in objects:
                    if not isinstance(obj, dict):
                        continue
                    obj_d = cast("dict[str, Any]", obj)
                    pkg: dict[str, Any] = cast("dict[str, Any]", obj_d.get("package") or {})
                    name = str(pkg.get("name") or "")
                    if name and name not in seen and any(name.startswith(p) for p in name_prefixes):
                        seen.add(name)
                        candidates.append(name)
                if len(objects) < _SEARCH_PAGE_SIZE:
                    break  # last page for this query
        return candidates, any_ok

    async def list_items(self, client: Any) -> AsyncIterator[RawItem]:
        """Enumerate candidates via search, then yield one RawItem per packument."""
        from app.db.session import AsyncSessionLocal
        from app.ingestion.framework.cursor import read_cursor, write_cursor

        search_url: str = self.config.discovery.get(
            "search_url", "https://registry.npmjs.org/-/v1/search"
        )
        registry_base: str = self.config.discovery.get(
            "registry_base", "https://registry.npmjs.org"
        )
        name_prefixes: list[str] = self.config.discovery.get("name_prefixes", [])
        # `search_queries` defaults to the prefixes themselves (good relevance text).
        queries: list[str] = self.config.discovery.get("search_queries", []) or name_prefixes
        max_items: int = int(self.config.discovery.get("max_items_per_cycle", 500))

        async with AsyncSessionLocal() as session:
            await read_cursor(session, self.config.name)

        items_yielded = 0
        # `completed` gates the terminal cursor write in the `finally` below: True ONLY
        # when the enumerate-then-fetch walk finishes naturally. A mid-walk exception or
        # worker-cancel/abandonment leaves it False → the cycle is recorded failed
        # (success=False), advancing the streak rather than silently greening a no-op.
        completed = False
        try:
            candidates, any_search_ok = await self._enumerate_candidates(
                client,
                search_url=search_url,
                queries=queries,
                name_prefixes=name_prefixes,
            )
            if not any_search_ok:
                # Every search request failed (registry down / rate-limited) — record the
                # cycle as failed (completed stays False) rather than silently greening a
                # no-op. A real 200 with zero matches still counts as `any_search_ok` and
                # completes successfully below.
                logger.warning("npm.search_all_failed", queries=len(queries))
                return
            for pkg_name in candidates:
                if items_yielded >= max_items:
                    break
                r = await client.get(_packument_url(registry_base, pkg_name))

                if r.status_code == 304:
                    yield RawItem(
                        source_id=f"npm/{pkg_name}",
                        raw_body_bytes=b"",
                        raw_body_hash=hashlib.sha256(b"").hexdigest(),
                        http_status=304,
                        etag=r.headers.get("etag"),
                        from_cache=True,
                        fetch_tier=1,
                    )
                    items_yielded += 1
                    continue

                if r.status_code != 200:
                    yield RawItem(
                        source_id=f"npm/{pkg_name}",
                        raw_body_bytes=r.content,
                        raw_body_hash=hashlib.sha256(r.content).hexdigest(),
                        http_status=r.status_code,
                        error_reason=("http_5xx" if r.status_code >= 500 else "other"),
                        fetch_tier=1,
                    )
                    items_yielded += 1
                    continue

                body = r.content
                try:
                    doc: dict[str, Any] = r.json()
                except Exception:
                    items_yielded += 1
                    continue

                yield RawItem(
                    source_id=f"npm/{pkg_name}",
                    raw_body_bytes=body,
                    raw_body_hash=hashlib.sha256(body).hexdigest(),
                    http_status=200,
                    etag=r.headers.get("etag"),
                    from_cache=False,
                    fetch_tier=1,
                    payload_hint=doc,
                )
                items_yielded += 1
            completed = True  # the enumerate-then-fetch walk finished without interruption
        finally:
            # Terminal cursor write on EVERY exit path — clean drain, mid-walk error, AND
            # worker-cancel/abandonment of this async generator (the `finally` runs on a
            # CancelledError/GeneratorExit too). `success=completed` resets the streak +
            # stamps `last_successful_cycle_at` only on a fully-walked cycle.
            async with AsyncSessionLocal() as session:
                await write_cursor(
                    session,
                    self.config.name,
                    {"last_cycle_items": items_yielded},
                    success=completed,
                )
                await session.commit()

    def normalize(self, raw: RawItem) -> NormalizedItem | None:
        """Map an npm package packument to a NormalizedItem.

        Unchanged from the `_changes` era — the search-API packument carries the same
        `dist-tags`/`versions`/`repository`/`license` fields the replication `doc` did.
        """
        if raw.http_status != 200:
            return None
        doc: dict[str, Any] = raw.payload_hint
        if not doc:
            return None

        pkg_name: str = str(doc.get("name") or "")
        if not pkg_name:
            return None

        # Latest dist-tag for metadata.
        dist_tags: dict[str, str] = doc.get("dist-tags") or {}
        latest_tag = dist_tags.get("latest") or ""
        versions: dict[str, Any] = doc.get("versions") or {}
        latest_meta: dict[str, Any] = versions.get(latest_tag) or {}

        description: str = (latest_meta.get("description") or doc.get("description") or "")[:280]

        # Resolve github coords from repository.url.
        repo_obj: Any = latest_meta.get("repository") or doc.get("repository") or {}
        repo_url = repo_obj if isinstance(repo_obj, str) else repo_obj.get("url") or ""
        github_org, github_repo = _parse_github_coords(repo_url)
        github_url = (
            f"https://github.com/{github_org}/{github_repo}" if github_org and github_repo else None
        )

        # License: prefer latest version's field.
        license_raw: Any = latest_meta.get("license") or doc.get("license")
        license_spdx: str | None = None
        if isinstance(license_raw, str):
            license_spdx = license_raw or None
        elif isinstance(license_raw, dict):
            _lic_dict: dict[str, Any] = cast("dict[str, Any]", license_raw)
            license_spdx = str(_lic_dict.get("type") or "") or None

        source_url = f"https://www.npmjs.com/package/{pkg_name}"

        return NormalizedItem(
            github_org=github_org,
            github_repo=github_repo,
            display_name=pkg_name,
            description=description,
            license_spdx=license_spdx,
            github_url=github_url,
            source_url=source_url,
            kind="mcp_server",
            metadata_files={},
            aggregator_listings=[self.config.name],
        )
