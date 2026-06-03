"""PyPI JSON API adapter.

Fetches the PyPI simple index, filters package names by the regex in
`discovery.name_regex`, then GETs `<json_base>/<name>/json` for each
candidate up to `max_items_per_cycle`. Persists the last-processed cursor
so re-runs are incremental.

Cadence: daily 02:00 UTC.
"""

from __future__ import annotations

import contextlib
import hashlib
import html.parser
import re
from collections.abc import AsyncIterator
from typing import Any

import structlog

from app.ingestion.config.loader import SourceConfig
from app.ingestion.framework.base_adapter import (
    NormalizedItem,
    RawItem,
    register_adapter,
)
from app.ingestion.framework.registry_adapter import RegistryAdapter

logger = structlog.get_logger(__name__)

_GITHUB_URL_RE = re.compile(r"https?://github\.com/([^/\s]+)/([^/\s\?#]+?)(?:\.git)?/?$")


def _parse_github_coords(url: str) -> tuple[str | None, str | None]:
    m = _GITHUB_URL_RE.match((url or "").strip())
    if m:
        return m.group(1), m.group(2)
    return None, None


class _SimpleIndexParser(html.parser.HTMLParser):
    """Minimal HTML parser to extract package names from the PyPI simple index."""

    def __init__(self) -> None:
        super().__init__()
        self.names: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    # href is like /simple/<name>/ — extract the package name.
                    parts = value.strip("/").split("/")
                    if parts:
                        self.names.append(parts[-1])


@register_adapter("pypi")
class PypiAdapter(RegistryAdapter):
    """Walk the PyPI simple index and fetch JSON metadata for matching packages."""

    def __init__(self, config: SourceConfig) -> None:
        super().__init__(config)

    async def list_items(self, client: Any) -> AsyncIterator[RawItem]:
        """Yield one RawItem per matching PyPI package JSON response."""
        from app.db.session import AsyncSessionLocal
        from app.ingestion.framework.cursor import read_cursor, write_cursor

        simple_index: str = self.config.discovery.get("simple_index", "https://pypi.org/simple/")
        json_base: str = self.config.discovery.get("json_base", "https://pypi.org/pypi")
        name_regex: str = self.config.discovery.get("name_regex", r"mcp")
        max_items: int = int(self.config.discovery.get("max_items_per_cycle", 2000))
        compiled = re.compile(name_regex, re.IGNORECASE)

        async with AsyncSessionLocal() as session:
            cursor = await read_cursor(session, self.config.name)

        last_processed: str = cursor.get("last_processed_name", "")
        items_yielded = 0
        new_last_processed = last_processed

        # Fetch the simple index to enumerate candidate package names.
        index_r = await client.get(
            simple_index,
            headers={"Accept": "text/html"},
        )
        if index_r.status_code not in (200, 304):
            yield RawItem(
                source_id="pypi/simple_index",
                raw_body_bytes=index_r.content,
                raw_body_hash=hashlib.sha256(index_r.content).hexdigest(),
                http_status=index_r.status_code,
                error_reason=("http_5xx" if index_r.status_code >= 500 else "other"),
                fetch_tier=1,
            )
            return

        # Parse package names from the HTML index.
        parser = _SimpleIndexParser()
        with contextlib.suppress(Exception):
            parser.feed(index_r.text)
        all_names = parser.names

        # Filter by regex and advance past the last-processed cursor.
        candidates = [n for n in all_names if compiled.search(n)]
        past_cursor = not last_processed
        for pkg_name in candidates:
            if not past_cursor:
                if pkg_name == last_processed:
                    past_cursor = True
                continue

            if items_yielded >= max_items:
                break

            pkg_url = f"{json_base.rstrip('/')}/{pkg_name}/json"
            r = await client.get(pkg_url)

            if r.status_code == 304:
                yield RawItem(
                    source_id=f"pypi/{pkg_name}",
                    raw_body_bytes=b"",
                    raw_body_hash=hashlib.sha256(b"").hexdigest(),
                    http_status=304,
                    etag=r.headers.get("etag"),
                    from_cache=True,
                    fetch_tier=1,
                )
                new_last_processed = pkg_name
                items_yielded += 1
                continue

            if r.status_code != 200:
                yield RawItem(
                    source_id=f"pypi/{pkg_name}",
                    raw_body_bytes=r.content,
                    raw_body_hash=hashlib.sha256(r.content).hexdigest(),
                    http_status=r.status_code,
                    error_reason=("http_5xx" if r.status_code >= 500 else "other"),
                    fetch_tier=1,
                )
                new_last_processed = pkg_name
                items_yielded += 1
                continue

            body = r.content
            try:
                data = r.json()
            except Exception:
                new_last_processed = pkg_name
                items_yielded += 1
                continue

            yield RawItem(
                source_id=f"pypi/{pkg_name}",
                raw_body_bytes=body,
                raw_body_hash=hashlib.sha256(body).hexdigest(),
                http_status=200,
                etag=r.headers.get("etag"),
                from_cache=False,
                fetch_tier=1,
                payload_hint=data,
            )
            new_last_processed = pkg_name
            items_yielded += 1

        async with AsyncSessionLocal() as session:
            await write_cursor(
                session,
                self.config.name,
                {"last_processed_name": new_last_processed},
                success=True,
            )
            await session.commit()

    def normalize(self, raw: RawItem) -> NormalizedItem | None:
        """Map a PyPI package JSON response to a NormalizedItem."""
        if raw.http_status != 200:
            return None
        data: dict[str, Any] = raw.payload_hint
        if not data:
            return None

        info: dict[str, Any] = data.get("info") or {}
        pkg_name: str = info.get("name") or ""
        if not pkg_name:
            return None

        description: str = (info.get("summary") or "")[:280]
        license_spdx: str | None = info.get("license") or None
        repo_yanked: bool = bool(info.get("yanked", False))

        # Try to extract GitHub coords from project_urls.
        project_urls: dict[str, str] = info.get("project_urls") or {}
        github_org: str | None = None
        github_repo: str | None = None
        github_url: str | None = None

        for key in ("Source", "Homepage", "Repository", "Source Code", "Code"):
            url_candidate = project_urls.get(key) or ""
            if "github.com" in url_candidate:
                github_org, github_repo = _parse_github_coords(url_candidate)
                if github_org and github_repo:
                    github_url = f"https://github.com/{github_org}/{github_repo}"
                    break

        # Infer kind: mcp_server if the name matches the mcp pattern, else skill.
        name_regex: str = self.config.discovery.get("name_regex", r"mcp")
        kind = "mcp_server" if re.search(name_regex, pkg_name, re.IGNORECASE) else "skill"

        source_url = f"https://pypi.org/project/{pkg_name}/"

        return NormalizedItem(
            github_org=github_org,
            github_repo=github_repo,
            display_name=pkg_name,
            description=description,
            license_spdx=license_spdx,
            github_url=github_url,
            source_url=source_url,
            kind=kind,
            repo_yanked=repo_yanked,
            metadata_files={},
            aggregator_listings=[self.config.name],
        )
