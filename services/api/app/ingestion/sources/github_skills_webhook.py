"""anthropics/skills GitHub push-webhook adapter.

Verifies X-Hub-Signature-256 (HMAC-SHA256 keyed on `settings.github_webhook_secret`).
For each touched `skills/<name>/` path in the push payload it fetches the skill's
manifest files from raw.githubusercontent.com and produces one (RawItem,
NormalizedItem) pair — the first touched skill only; additional skills in the same
push are enqueued as separate tasks by the webhook router.

The adapter is webhook-driven (CADENCE_CRON is null in its YAML); list_items and
normalize are no-ops inherited from WebhookAdapter.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, cast

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.config.loader import SourceConfig
from app.ingestion.framework.base_adapter import (
    NormalizedItem,
    RawItem,
    register_adapter,
)
from app.ingestion.framework.webhook_adapter import WebhookAdapter

logger = structlog.get_logger(__name__)


def _extract_description(body: bytes) -> str:
    """Extract a ≤280-char description from a README/SKILL.md body."""
    if not body:
        return ""
    try:
        text = body.decode("utf-8", errors="ignore")
    except Exception:
        return ""
    # Take the first non-empty paragraph after the first H1 heading.
    paragraph = ""
    in_paragraph = False
    for line in text.splitlines():
        stripped = line.strip()
        if not in_paragraph:
            if stripped.startswith("# "):
                in_paragraph = True
        else:
            if not stripped:
                break
            paragraph += " " + stripped
    paragraph = paragraph.strip()
    if len(paragraph) > 280:
        paragraph = paragraph[:277].rsplit(" ", 1)[0] + "…"
    return paragraph


@register_adapter("github_skills")
class GithubSkillsWebhookAdapter(WebhookAdapter):
    """Translate anthropics/skills push events into (RawItem, NormalizedItem) pairs."""

    def __init__(self, config: SourceConfig) -> None:
        super().__init__(config)

    @classmethod
    def verify_signature(cls, raw_body: bytes, sig_header: str | None) -> bool:
        """Return True iff the HMAC-SHA256 signature on raw_body matches sig_header.

        Returns False when the webhook secret is not configured or the header is
        absent/malformed — fail-closed.
        """
        from app.core.config import get_settings

        secret = get_settings().github_webhook_secret
        if not secret:
            return False
        if not sig_header or not sig_header.startswith("sha256="):
            return False
        expected = (
            "sha256="
            + hmac.new(
                secret.encode("utf-8"),
                raw_body,
                hashlib.sha256,
            ).hexdigest()
        )
        return hmac.compare_digest(expected, sig_header)

    async def handle_webhook(
        self,
        payload: dict[str, Any],
        session: AsyncSession,
    ) -> tuple[RawItem, NormalizedItem | None]:
        """Translate a push payload into (RawItem, NormalizedItem|None).

        Returns a no-op RawItem (http_status=0) when no skills/ paths are touched.
        """
        from app.core.config import get_settings
        from app.ingestion.framework.http_client import HttpClientFactory

        skill_path_prefix: str = self.config.discovery.get("skill_path_prefix", "skills/")
        manifest_files_list: list[str] = self.config.discovery.get(
            "manifest_files", ["SKILL.md", "skill.yaml", "README.md", "mcp.json"]
        )

        # Collect skill names touched in this push.
        touched: set[str] = set()
        commits_raw: Any = payload.get("commits")
        commits: list[dict[str, Any]] = (
            cast("list[dict[str, Any]]", commits_raw) if isinstance(commits_raw, list) else []
        )
        for commit in commits:
            added: list[str] = list(commit.get("added") or [])
            modified: list[str] = list(commit.get("modified") or [])
            for path in added + modified:
                if path.startswith(skill_path_prefix):
                    remainder: str = path[len(skill_path_prefix) :]
                    if "/" in remainder:
                        skill_name: str = remainder.split("/", 1)[0]
                        touched.add(skill_name)

        if not touched:
            raw_body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
            return (
                RawItem(
                    source_id=f"{payload.get('repository', {}).get('full_name', 'unknown')}/__noop__",
                    raw_body_bytes=raw_body,
                    raw_body_hash=hashlib.sha256(raw_body).hexdigest(),
                    http_status=0,
                    fetch_tier=0,
                ),
                None,
            )

        # Process the first touched skill; additional ones are fanned out by the router.
        first_skill = sorted(touched)[0]
        repo_obj: dict[str, Any] = payload.get("repository") or {}
        repo_full: str = repo_obj.get("full_name", "")
        owner: str = repo_obj.get("owner", {}).get("login", "")
        _after: Any = payload.get("after")
        _head_commit_raw: Any = payload.get("head_commit")
        _head_commit: dict[str, Any] = (
            cast(dict[str, Any], _head_commit_raw) if isinstance(_head_commit_raw, dict) else {}
        )
        _head_id: Any = _head_commit.get("id")
        ref_sha: str = str(_after or _head_id or "main")
        default_branch: str = repo_obj.get("default_branch", "main")

        # Fetch manifest files from raw.githubusercontent.com.
        settings = get_settings()
        client = HttpClientFactory.build(self, settings)
        manifest_files: dict[str, bytes] = {}
        async with client:
            for filename in manifest_files_list:
                url = (
                    f"https://raw.githubusercontent.com/"
                    f"{repo_full}/{ref_sha}/{skill_path_prefix}{first_skill}/{filename}"
                )
                try:
                    r = await client.get(url)
                    if r.status_code == 200:
                        manifest_files[filename] = r.content
                except Exception:
                    pass

        # Build description from README then SKILL.md.
        description = _extract_description(
            manifest_files.get("README.md") or manifest_files.get("SKILL.md") or b""
        )

        raw_body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        raw = RawItem(
            source_id=f"{repo_full}/{first_skill}",
            raw_body_bytes=raw_body,
            raw_body_hash=hashlib.sha256(raw_body).hexdigest(),
            http_status=200,
            fetch_tier=0,
        )
        normalized = NormalizedItem(
            github_org=owner,
            github_repo=f"skills--{first_skill}",
            display_name=first_skill,
            description=description,
            license_spdx="Apache-2.0",
            github_url=(
                f"https://github.com/{repo_full}/tree/main/{skill_path_prefix}{first_skill}"
            ),
            source_url=None,
            stars=repo_obj.get("stargazers_count"),
            pushed_at=payload.get("pushed_at"),
            default_branch=default_branch,
            metadata_files=manifest_files,
            aggregator_listings=[self.config.name],
            kind="skill",
        )
        return raw, normalized
