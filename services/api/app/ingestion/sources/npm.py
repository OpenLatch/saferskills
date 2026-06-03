"""npm replication _changes stream adapter.

Streams `replicate.npmjs.com/_changes?since=<seq>&include_docs=true
&feed=continuous&heartbeat=30000`, keeping only packages whose name starts with
any prefix in `discovery.name_prefixes`. Persists the last `seq` as the cursor.

Cadence: hourly at :00 UTC.
"""

from __future__ import annotations

import hashlib
import json
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


def _parse_github_coords(repo_url: str) -> tuple[str | None, str | None]:
    for pattern in (_GITHUB_REPO_RE, _GITHUB_SSH_RE):
        m = pattern.match(repo_url.strip())
        if m:
            return m.group(1), m.group(2)
    return None, None


@register_adapter("npm")
class NpmAdapter(RegistryAdapter):
    """Stream the npm replication _changes feed for MCP/skill packages."""

    def __init__(self, config: SourceConfig) -> None:
        super().__init__(config)

    async def list_items(self, client: Any) -> AsyncIterator[RawItem]:
        """Stream the continuous changes feed, yielding matching package docs."""
        from app.db.session import AsyncSessionLocal
        from app.ingestion.framework.cursor import read_cursor, write_cursor

        changes_url: str = self.config.discovery.get(
            "changes_url", "https://replicate.npmjs.com/_changes"
        )
        name_prefixes: list[str] = self.config.discovery.get("name_prefixes", [])
        max_items: int = int(self.config.discovery.get("max_items_per_cycle", 5000))

        async with AsyncSessionLocal() as session:
            cursor = await read_cursor(session, self.config.name)

        last_seq = cursor.get("seq", 0)
        items_yielded = 0

        try:
            async with client.stream(
                "GET",
                changes_url,
                params={
                    "since": str(last_seq),
                    "include_docs": "true",
                    "feed": "continuous",
                    "heartbeat": "30000",
                },
            ) as r:
                async for line in r.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        _entry: Any = json.loads(line)
                        entry: dict[str, Any] = (
                            cast("dict[str, Any]", _entry) if isinstance(_entry, dict) else {}
                        )
                    except json.JSONDecodeError:
                        continue
                    seq: Any = entry.get("seq")
                    _doc: Any = entry.get("doc")
                    doc: dict[str, Any] = (
                        cast("dict[str, Any]", _doc) if isinstance(_doc, dict) else {}
                    )
                    pkg_name: str = str(doc.get("name") or "")
                    if not pkg_name:
                        # Heartbeat / no doc — advance seq but don't yield.
                        if seq is not None:
                            last_seq = seq
                        continue

                    # Filter by name prefix.
                    if not any(pkg_name.startswith(p) for p in name_prefixes):
                        if seq is not None:
                            last_seq = seq
                        continue

                    body = json.dumps(doc, separators=(",", ":"), sort_keys=True).encode()
                    yield RawItem(
                        source_id=f"npm/{pkg_name}",
                        raw_body_bytes=body,
                        raw_body_hash=hashlib.sha256(body).hexdigest(),
                        http_status=200,
                        fetch_tier=1,
                        payload_hint=doc,
                    )
                    if seq is not None:
                        last_seq = seq
                    items_yielded += 1
                    if items_yielded >= max_items:
                        break
        except Exception:
            # Stream closed or network error — persist what we have.
            logger.warning("npm.stream_interrupted", last_seq=last_seq)

        async with AsyncSessionLocal() as session:
            await write_cursor(
                session,
                self.config.name,
                {"seq": last_seq},
                success=True,
            )
            await session.commit()

    def normalize(self, raw: RawItem) -> NormalizedItem | None:
        """Map an npm package doc to a NormalizedItem."""
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
