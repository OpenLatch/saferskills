"""Regression (I-5.6 D-5.6-17 / Codex P0-1): the Agent Report DTO carries WEB-page
`report_url`/`share_url` at `/agents/*`, NOT the API prefix `/agent-scans/*`.

`report_url`/`share_url` feed the share button, the badge reproducibility line, and
`EmbedBadgeBox`. The web routes are `/agents/{id}` + `/agents/r/{token}` (D-5.6-01),
while the API stays `/api/v1/agent-scans/*` — if the builder emits `/agent-scans/…`
as the page URL, every share link 404s.

The builder reads only attributes, so a `SimpleNamespace` stands in for the ORM
`AgentRun` — no DB needed (mirrors `tests/scan/test_report_url.py`). `status` is a
pre-grade value so `_build_checks` returns `[]` without loading the pack.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

from app.agent_scan.report import (
    _public_report_url,  # pyright: ignore[reportPrivateUsage]
    _share_url,  # pyright: ignore[reportPrivateUsage]
    build_agent_report,
    report_urls,
)
from app.core.config import get_settings
from app.models.generated.agent_run import AgentRun

_RUN_ID = uuid.UUID("018e7c8b-aaaa-7000-8000-000000000001")
_TOKEN = "Hh3y6Qk2pN8fT0aZ1cV9bWx"


def _run(*, share_token: str | None, visibility: str) -> AgentRun:
    ns = SimpleNamespace(
        id=_RUN_ID,
        status="created",  # pre-grade → _build_checks returns [] (no pack load)
        agent_name="acme-coding-agent",
        runtime="claude-code",
        score=None,
        band="unscoped",
        verdict_label=None,
        cap_callout=None,
        confidence=None,
        score_breakdown=None,
        trust_labels=[],
        pack_id="saferskills-agent-baseline",
        pack_version="2026.06.09",
        pack_signature_verified=None,
        capabilities_present=[],
        capabilities_absent=[],
        family_tally={},
        visibility=visibility,
        expires_at=None,
        share_token=share_token,
        rubric_version="a1b2c3d",
        engine_version="def5678",
        latency_ms=0,
        scanned_at=datetime(2026, 6, 9, tzinfo=UTC),
        vendor_reply=None,
        vendor_reply_at=None,
    )
    return cast(AgentRun, ns)


def test_public_report_url_points_at_web_agents_route() -> None:
    base = get_settings().public_base_url.rstrip("/")
    url = _public_report_url(get_settings(), _run(share_token=None, visibility="public"))
    assert url == f"{base}/agents/{_RUN_ID}"
    assert "/agent-scans/" not in url
    assert "/agents/r/" not in url


def test_share_url_points_at_web_agents_token_route() -> None:
    base = get_settings().public_base_url.rstrip("/")
    assert _share_url(get_settings(), None) is None
    url = _share_url(get_settings(), _TOKEN)
    assert url is not None
    assert url == f"{base}/agents/r/{_TOKEN}"
    assert "/agent-scans/" not in url


def test_report_urls_public_vs_private() -> None:
    settings = get_settings()
    base = settings.public_base_url.rstrip("/")

    pub_report, pub_share = report_urls(
        _run(share_token=None, visibility="public"), settings, private=False
    )
    assert pub_report == f"{base}/agents/{_RUN_ID}"
    assert pub_share is None

    priv_report, priv_share = report_urls(
        _run(share_token=_TOKEN, visibility="unlisted"), settings, private=True
    )
    assert priv_report == priv_share == f"{base}/agents/r/{_TOKEN}"


def test_build_agent_report_dto_carries_web_urls() -> None:
    settings = get_settings()
    base = settings.public_base_url.rstrip("/")
    report = build_agent_report(
        _run(share_token=None, visibility="public"), [], settings=settings, private=False
    )
    assert report.report_url == f"{base}/agents/{_RUN_ID}"
    assert "/agent-scans/" not in (report.report_url or "")
