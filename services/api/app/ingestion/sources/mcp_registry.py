"""Official MCP Registry poll adapter (registry.modelcontextprotocol.io).

Cursor-paginates `GET /v0/servers?updated_since=<cursor>&cursor=<opaque>`,
persisting the high-water `updated_since` timestamp after each cycle.

Cadence: hourly at :00 UTC.
"""

from __future__ import annotations

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

logger = structlog.get_logger(__name__)

_GITHUB_URL_PREFIXES = (
    "https://github.com/",
    "git+https://github.com/",
    "git://github.com/",
)


def _parse_github_coords(url: str) -> tuple[str | None, str | None]:
    """Extract (org, repo) from a GitHub URL, stripping .git and trailing slashes."""
    for prefix in _GITHUB_URL_PREFIXES:
        if url.startswith(prefix):
            path = url[len(prefix) :].rstrip("/").removesuffix(".git")
            parts = path.split("/", 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                return parts[0], parts[1]
    return None, None


def _parse_name_coords(name: str) -> tuple[str | None, str | None]:
    """Extract (org, repo) from an MCP Registry `name` ONLY when it is GitHub-namespaced.

    Registry names are reverse-DNS namespaced — `io.github.<org>/<repo>` is the one
    namespace that maps to a real GitHub repo. Any other `<namespace>/<name>` (e.g.
    `ac.tandem/docs-mcp`) is NOT a GitHub coordinate; treating it as one would mint a
    fake `github.com/<namespace>/<name>` identity. Repo-less servers fall through to
    the no-GitHub-URL path (fuzzy queue).
    """
    if name.startswith("io.github."):
        rest = name[len("io.github.") :]
        parts = rest.split("/", 1)
        if len(parts) == 2 and parts[0] and parts[1]:
            return parts[0], parts[1]
    return None, None


@register_adapter("mcp_registry")
class McpRegistryAdapter(RegistryAdapter):
    """Poll the official MCP Registry /v0/servers endpoint by updated_since cursor."""

    def __init__(self, config: SourceConfig) -> None:
        super().__init__(config)

    async def list_items(self, client: Any) -> AsyncIterator[RawItem]:
        """Yield one RawItem per server record, advancing the opaque cursor.

        The full-feed sweep (~12k servers, each enriched with several sequential
        GitHub/raw fetches) takes far longer than a `--reload` / restart / the 4h
        stalled-retry survive, so the resume marker is **checkpointed per page**
        (`save_cursor_progress`, health-neutral) BEFORE the page is fetched: an
        aborted cycle resumes from the last page instead of re-crawling from the
        epoch (the never-completing zombie loop). The high-water `updated_since`
        watermark is only advanced — and the cycle marked successful — by
        `write_cursor` once the sweep completes naturally (or a 304 says nothing is
        new). A transport error (5xx / rate-limit) leaves the checkpoint in place so
        the next cycle resumes, and does NOT falsely mark the cycle successful.
        """
        from app.db.session import AsyncSessionLocal
        from app.ingestion.framework.cursor import (
            read_cursor,
            save_cursor_progress,
            write_cursor,
        )

        api_base: str = self.config.discovery.get(
            "api_base", "https://registry.modelcontextprotocol.io"
        )
        servers_path: str = self.config.discovery.get("servers_path", "/v0/servers")
        url = api_base.rstrip("/") + servers_path

        async with AsyncSessionLocal() as session:
            cursor = await read_cursor(session, self.config.name)

        page_limit = int(self.config.discovery.get("page_limit", 100))
        updated_since: str = cursor.get("updated_since", "1970-01-01T00:00:00Z")
        opaque_cursor: str | None = cursor.get("next_cursor")
        new_high_water: str = updated_since

        async def _checkpoint(next_cursor: str | None) -> None:
            """Persist the resume marker (lagging — written before the page it points
            to is processed, so a mid-page abort re-fetches that page rather than
            skipping it; the merger upsert is idempotent)."""
            async with AsyncSessionLocal() as cp_session:
                await save_cursor_progress(
                    cp_session,
                    self.config.name,
                    {"updated_since": updated_since, "next_cursor": next_cursor},
                )
                await cp_session.commit()

        sweep_complete = False
        try:
            while True:
                # Checkpoint the page we are ABOUT to fetch (resume point on abort).
                await _checkpoint(opaque_cursor)

                params: dict[str, str] = {
                    "updated_since": updated_since,
                    "limit": str(page_limit),
                }
                if opaque_cursor:
                    params["cursor"] = opaque_cursor

                r = await client.get(url, params=params)

                if r.status_code == 304:
                    yield RawItem(
                        source_id=f"mcp_registry/cursor:{opaque_cursor or 'start'}",
                        raw_body_bytes=b"",
                        raw_body_hash=hashlib.sha256(b"").hexdigest(),
                        http_status=304,
                        etag=r.headers.get("etag"),
                        from_cache=True,
                        fetch_tier=1,
                    )
                    sweep_complete = True  # nothing new since the watermark
                    break

                if r.status_code != 200:
                    yield RawItem(
                        source_id=f"mcp_registry/cursor:{opaque_cursor or 'start'}",
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
                    # Transient fetch failure — keep the checkpoint, do NOT complete.
                    break

                data = r.json()
                servers: list[dict[str, Any]] = data.get("servers") or []
                for record in servers:
                    # The /v0/servers feed wraps each entry: the server object lives
                    # under `server`, registry bookkeeping under `_meta`. Unwrap both
                    # (fall back to the bare record if an older shape ever reappears).
                    inner: Any = record.get("server")
                    server: dict[str, Any] = (
                        cast("dict[str, Any]", inner) if isinstance(inner, dict) else record
                    )
                    meta_raw: Any = record.get("_meta")
                    meta_outer: dict[str, Any] = (
                        cast("dict[str, Any]", meta_raw) if isinstance(meta_raw, dict) else {}
                    )
                    meta_inner: Any = meta_outer.get("io.modelcontextprotocol.registry/official")
                    meta: dict[str, Any] = (
                        cast("dict[str, Any]", meta_inner) if isinstance(meta_inner, dict) else {}
                    )

                    # Latest version only — the feed returns every published version.
                    if meta.get("isLatest") is False:
                        continue

                    body = json.dumps(server, separators=(",", ":"), sort_keys=True).encode()
                    server_id: str = (
                        str(server.get("name") or "") or hashlib.sha256(body).hexdigest()[:16]
                    )
                    updated_at: str = str(meta.get("updatedAt") or meta.get("updated_at") or "")
                    if updated_at > new_high_water:
                        new_high_water = updated_at
                    yield RawItem(
                        source_id=f"mcp_registry/{server_id}",
                        raw_body_bytes=body,
                        raw_body_hash=hashlib.sha256(body).hexdigest(),
                        http_status=200,
                        fetched_at=dt.datetime.now(tz=dt.UTC).isoformat(),
                        from_cache=False,
                        fetch_tier=1,
                        payload_hint=server,
                    )

                page_meta: dict[str, Any] = data.get("metadata") or {}
                opaque_cursor = page_meta.get("nextCursor") or page_meta.get("next_cursor")
                if not opaque_cursor:
                    sweep_complete = True
                    break
        finally:
            # Terminal write is `finally`-guarded so it runs on every exit path,
            # INCLUDING worker-cancel/abandonment of this async generator — but the
            # split is unchanged: ONLY a fully-drained feed (or a 304) advances the
            # watermark, marks the cycle successful, and clears the resume cursor
            # (`if sweep_complete`). A mid-sweep abort / transport error / cancel
            # leaves the last per-page checkpoint untouched (no success write), so the
            # next cycle resumes from there instead of restarting at the epoch.
            if sweep_complete:
                async with AsyncSessionLocal() as session:
                    await write_cursor(
                        session,
                        self.config.name,
                        {"updated_since": new_high_water, "next_cursor": None},
                        success=True,
                    )
                    await session.commit()

    def normalize(self, raw: RawItem) -> NormalizedItem | None:
        """Map an MCP Registry server record to a NormalizedItem."""
        if raw.http_status != 200:
            return None
        # payload_hint is the unwrapped `server` object (see list_items).
        server: dict[str, Any] = raw.payload_hint
        if not isinstance(server, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
            return None

        name: str = str(server.get("name") or "")
        description: str = (server.get("description") or "")[:280]
        github_org: str | None = None
        github_repo: str | None = None
        github_url: str | None = None

        # Try repository.url first, then fall back to a GitHub-namespaced name.
        repo_obj: dict[str, Any] = server.get("repository") or {}
        repo_url: str = repo_obj.get("url") or ""
        if repo_url:
            github_org, github_repo = _parse_github_coords(repo_url)

        if not github_org or not github_repo:
            github_org, github_repo = _parse_name_coords(name)

        if github_org and github_repo:
            github_url = f"https://github.com/{github_org}/{github_repo}"

        # Prefer the human-readable title; fall back to the last name segment.
        display_name = server.get("title") or name.split("/")[-1] or name or "unknown"

        # No per-server public permalink is exposed (by-name lookups 404); credit the
        # registry root as the source backlink.
        api_base: str = self.config.discovery.get(
            "api_base", "https://registry.modelcontextprotocol.io"
        )
        source_url: str | None = api_base.rstrip("/")

        return NormalizedItem(
            github_org=github_org,
            github_repo=github_repo,
            display_name=display_name,
            description=description,
            license_spdx=None,
            github_url=github_url,
            source_url=source_url,
            kind="mcp_server",
            metadata_files={},  # populated by enrich()
            aggregator_listings=[self.config.name],
        )

    async def enrich(self, client: Any, normalized: NormalizedItem) -> None:
        """Fetch GitHub repo facts + manifest/README so the quality classifier can
        tier registry servers instead of defaulting every one to `empty`.

        The /v0/servers feed carries no repo signals, so `classify_quality_tier`
        sees `is_empty=True` for every item and the default catalog gate
        (`quality_tier IN ('high','medium')`) hides the whole catalog.
        This pass populates `stars` + a `commit_count` proxy (repo `size`) +
        manifest/README bytes so a real listing tiers to `medium`/`high`.

        Best-effort: any fetch failure leaves the item as the feed presented it
        (still indexable, just lower-tier). Mirrors `github_topics.enrich`.
        """
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
                # GitHub repo `size` (KB) is the same commit-count proxy
                # github_topics uses — a non-zero size lifts an item out of `empty`.
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
            logger.debug("mcp_registry.enrich_repo_meta_failed", org=org, repo=repo)

        branch = normalized.default_branch or "main"
        for filename in ("mcp.json", "server.json", "README.md"):
            url = f"https://raw.githubusercontent.com/{org}/{repo}/{branch}/{filename}"
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    normalized.metadata_files[filename] = r.content
            except Exception:
                logger.debug("mcp_registry.enrich_file_failed", org=org, repo=repo, file=filename)
