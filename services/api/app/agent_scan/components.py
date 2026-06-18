"""Component-score projection for the Agent Report.

The Agent Report's **Component Scores** tab lists every capability the scanned
agent has assembled (skills, MCP servers, hooks, plugins, rules), each with its own
static score + a "View report ->" deep-link. The data is captured best-effort by the
`saferskills agent` CLI: it `scan --local`-uploads the scanned platform's installed
capabilities, links that `scan_run` onto the agent run (`agent_runs.component_scan_
run_id`), and the report projects that run's per-capability `scans` into rows here.

Web-initiated scans (`/agents/scan`, the picker) + `--print-skill` have no local
filesystem, so `component_scan_run_id` is null and the tab keeps its honest
"Behavior graded as one system" empty state.

No raw payload: a row carries only kind/name/path/score/tier/
slug — derived metadata, never a transcript or finding body.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_scan.report import build_agent_report
from app.core.config import Settings
from app.models.generated.agent_finding import AgentFinding
from app.models.generated.agent_run import AgentRun
from app.models.generated.catalog_item import CatalogItem
from app.models.generated.scan import Scan
from app.models.generated.scan_run import ScanRun
from app.schemas.agent_scan import AgentScanReportDetail

# Display order in the Component Scores table (mirrors the mockup): mcp -> skill ->
# hook -> plugin -> rules, then worst-score-first within a kind.
_KIND_ORDER: dict[str, int] = {
    "mcp_server": 0,
    "skill": 1,
    "hook": 2,
    "plugin": 3,
    "rules": 4,
}


async def load_component_scores(
    session: AsyncSession, run: AgentRun, settings: Settings, *, private: bool
) -> tuple[list[dict[str, Any]], str | None]:
    """Project the linked component `scan_run`'s per-capability `scans` to rows.

    Returns `(rows, component_report_url)`:
    - `rows` is one `AgentComponentScoreRow`-shaped dict per scanned capability
      (kind/name/path/score/tier/slug), sorted by `_KIND_ORDER` then worst-first.
    - `component_report_url` is the unlisted component scan_run's `/scans/r/<token>`
      report (every row deep-links there for an unlisted agent run, since its shadow
      catalog items 404 on the public catalog); `None` for a public run (rows link
      to their real `/items/<slug>`).

    A null/absent link, a missing scan_run, or a still-running component scan all
    yield `([], None)` — the tab falls back to its honest empty state.
    """
    if run.component_scan_run_id is None:
        return [], None
    scan_run = await session.get(ScanRun, run.component_scan_run_id)
    if scan_run is None:
        return [], None

    rows = (
        await session.execute(
            select(Scan, CatalogItem)
            .join(CatalogItem, Scan.catalog_item_id == CatalogItem.id)
            .where(Scan.scan_run_id == run.component_scan_run_id)
        )
    ).all()

    component_report_url: str | None = None
    if private and scan_run.visibility == "unlisted" and scan_run.share_token:
        base = settings.public_base_url.rstrip("/")
        component_report_url = f"{base}/scans/r/{scan_run.share_token}"

    out: list[dict[str, Any]] = [
        {
            "kind": item.kind,
            "name": item.display_name,
            "path": scan.component_path or None,
            "score": scan.aggregate_score,
            "tier": scan.tier,
            "slug": item.slug,
        }
        for scan, item in rows
    ]
    out.sort(key=lambda r: (_KIND_ORDER.get(str(r["kind"]), 99), int(r["score"])))
    return out, component_report_url


async def render_agent_report(
    session: AsyncSession,
    run: AgentRun,
    findings: list[AgentFinding],
    *,
    settings: Settings,
    private: bool,
    evidence: dict[str, Any] | None = None,
) -> AgentScanReportDetail:
    """Build the wire report with its component scores loaded from the DB.

    The async companion to `report.build_agent_report` (which stays pure/sync for
    unit testing): it resolves the linked component scan_run, then delegates. Every
    router report-build path goes through here so component scores + the unlisted
    deep-link are projected uniformly.
    """
    component_scores, component_report_url = await load_component_scores(
        session, run, settings, private=private
    )
    return build_agent_report(
        run,
        findings,
        settings=settings,
        private=private,
        evidence=evidence,
        component_scores=component_scores,
        component_report_url=component_report_url,
    )
