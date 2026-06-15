"""Public Agent Report directory queries (I-5.6 Phase C, D-5.6-05).

The `/agents` directory + the corpus risk meter read `agent_runs` directly — an
Agent Report is its own entity, never a `catalog_items` row. Every query here is
PUBLIC-ONLY: `visibility='public' AND status IN ('graded','published') AND score
IS NOT NULL`. Visibility alone would leak created/submitted/ungraded null-score
runs into the grid + the aggregate stat (Codex P1).

No raw payload (prime invariant #3): a summary carries only derived counts/labels
(severity tally, trust tier), never a transcript or finding body.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, and_, asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_scan.report import report_urls
from app.core.config import Settings
from app.models.generated.agent_finding import AgentFinding
from app.models.generated.agent_run import AgentRun
from app.schemas.agent_scan import (
    AgentAggregateStats,
    AgentBandDistribution,
    AgentBandShare,
    AgentCapabilityTally,
    AgentFindingsSummary,
    AgentScanListEnvelope,
    AgentScanSummary,
)

# Period windows (design §5). 'all'/unselected = no time filter. Sort keys are
# `newest` (default) | `score_asc` | `score_desc`; severity filters are
# critical/high/info/no-findings — both validated at the router boundary.
_PERIOD_DAYS: dict[str, int] = {"24h": 1, "7d": 7, "30d": 30, "quarter": 90}

_MAX_PAGE_SIZE = 60


def _public_graded() -> ColumnElement[bool]:
    """The public-only + graded + scored predicate shared by every directory query."""
    return and_(
        AgentRun.visibility == "public",
        AgentRun.status.in_(("graded", "published")),
        AgentRun.score.is_not(None),
    )


def _period_cutoff(periods: list[str]) -> datetime | None:
    """The broadest selected window's cutoff (most-inclusive); None = all time."""
    days = [_PERIOD_DAYS[p] for p in periods if p in _PERIOD_DAYS]
    if not days:
        return None
    return datetime.now(UTC) - timedelta(days=max(days))


def _severity_condition(severities: list[str]) -> ColumnElement[bool] | None:
    """OR over the selected severity filters via correlated EXISTS / NOT EXISTS."""
    conds: list[ColumnElement[bool]] = []
    for sev in severities:
        if sev == "no-findings":
            conds.append(
                ~select(AgentFinding.id).where(AgentFinding.agent_run_id == AgentRun.id).exists()
            )
        elif sev in ("critical", "high", "info"):
            conds.append(
                select(AgentFinding.id)
                .where(
                    and_(
                        AgentFinding.agent_run_id == AgentRun.id,
                        AgentFinding.severity == sev,
                    )
                )
                .exists()
            )
    if not conds:
        return None
    return or_(*conds)


def _filters(
    *,
    q: str | None,
    score_min: int | None,
    score_max: int | None,
    periods: list[str],
    runtimes: list[str],
    severities: list[str],
) -> list[ColumnElement[bool]]:
    clauses: list[ColumnElement[bool]] = [_public_graded()]
    if q and q.strip():
        # Escape LIKE wildcards so user input is matched literally.
        needle = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append(AgentRun.agent_name.ilike(f"%{needle}%", escape="\\"))
    if score_min is not None:
        clauses.append(AgentRun.score >= score_min)
    if score_max is not None:
        clauses.append(AgentRun.score <= score_max)
    cutoff = _period_cutoff(periods)
    if cutoff is not None:
        clauses.append(AgentRun.scanned_at >= cutoff)
    if runtimes:
        clauses.append(AgentRun.runtime.in_(runtimes))
    sev = _severity_condition(severities)
    if sev is not None:
        clauses.append(sev)
    return clauses


def _order_by(sort: str) -> list[ColumnElement[object]]:
    if sort == "score_asc":
        return [asc(AgentRun.score), desc(AgentRun.scanned_at), desc(AgentRun.id)]
    if sort == "score_desc":
        return [desc(AgentRun.score), desc(AgentRun.scanned_at), desc(AgentRun.id)]
    # newest (default) — latest-first leaderboard-avoiding order.
    return [desc(AgentRun.scanned_at), desc(AgentRun.id)]


def _trust_tier(trust_labels: list[str] | None) -> str | None:
    """The dossier-card trust tier — the launch posture's primary label."""
    labels = trust_labels or []
    if "cloud-validated" in labels:
        return "cloud-validated"
    return labels[0] if labels else None


def _capability_tally(kind_tally: dict[str, Any] | None) -> AgentCapabilityTally:
    """Project the DB-only `agent_runs.kind_tally` JSONB onto the wire tally.

    NULL/absent → an all-zero tally (no icons), which is correct until a real
    component inventory is captured. Keys are exactly skill/hook/mcp/plugin/rules.
    """
    kt = kind_tally or {}
    return AgentCapabilityTally(
        skill=int(kt.get("skill", 0)),
        hook=int(kt.get("hook", 0)),
        mcp=int(kt.get("mcp", 0)),
        plugin=int(kt.get("plugin", 0)),
        rules=int(kt.get("rules", 0)),
    )


async def _findings_by_run(
    session: AsyncSession, run_ids: list[UUID]
) -> dict[UUID, AgentFindingsSummary]:
    """Per-run severity tally (critical/high/info/total) for a page of runs."""
    if not run_ids:
        return {}
    rows = await session.execute(
        select(AgentFinding.agent_run_id, AgentFinding.severity, func.count())
        .where(AgentFinding.agent_run_id.in_(run_ids))
        .group_by(AgentFinding.agent_run_id, AgentFinding.severity)
    )
    acc: dict[UUID, AgentFindingsSummary] = {rid: AgentFindingsSummary() for rid in run_ids}
    for run_id, severity, count in rows:
        summary = acc[run_id]
        summary.total += count
        if severity == "critical":
            summary.critical += count
        elif severity == "high":
            summary.high += count
        elif severity == "info":
            summary.info += count
    return acc


async def list_public_runs(
    session: AsyncSession,
    settings: Settings,
    *,
    q: str | None = None,
    score_min: int | None = None,
    score_max: int | None = None,
    periods: list[str] | None = None,
    runtimes: list[str] | None = None,
    severities: list[str] | None = None,
    sort: str = "newest",
    page: int = 1,
    page_size: int = 24,
) -> AgentScanListEnvelope:
    """Paginated, filterable, public-only dossier list (the `/agents` grid)."""
    page = max(1, page)
    page_size = max(1, min(page_size, _MAX_PAGE_SIZE))
    clauses = _filters(
        q=q,
        score_min=score_min,
        score_max=score_max,
        periods=periods or [],
        runtimes=runtimes or [],
        severities=severities or [],
    )

    total_count = (
        await session.execute(select(func.count()).select_from(AgentRun).where(*clauses))
    ).scalar_one()

    rows = (
        (
            await session.execute(
                select(AgentRun)
                .where(*clauses)
                .order_by(*_order_by(sort))
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    tallies = await _findings_by_run(session, [run.id for run in rows])
    data = [
        AgentScanSummary(
            id=str(run.id),
            agent_name=run.agent_name,
            runtime=run.runtime,
            score=run.score,
            band=run.band,  # type: ignore[arg-type]
            report_url=report_urls(run, settings, private=False)[0],
            scanned_at=run.scanned_at,
            capability_tally=_capability_tally(run.kind_tally),
            findings_summary=tallies.get(run.id, AgentFindingsSummary()),
            trust_tier=_trust_tier(run.trust_labels),
        )
        for run in rows
    ]

    total_pages = max(1, (total_count + page_size - 1) // page_size)
    return AgentScanListEnvelope(
        data=data,
        total_count=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


async def aggregate_stats(session: AsyncSession, settings: Settings) -> AgentAggregateStats:
    """Corpus risk meter feed — gated until the corpus reaches `AGENT_CORPUS_GATE_N`."""
    base = _public_graded()
    band_rows = await session.execute(
        select(AgentRun.band, func.count()).where(base).group_by(AgentRun.band)
    )
    band_counts: dict[str, int] = {band: count for band, count in band_rows}
    # The band column is NOT NULL on every graded+scored run, so the GROUP-BY
    # already partitions the whole filtered set — corpus_count is its sum (one
    # fewer round-trip than a separate COUNT(*)).
    corpus_count = sum(band_counts.values())
    gate_target = settings.agent_corpus_gate_n
    gate_met = corpus_count >= gate_target

    def share(band: str) -> AgentBandShare:
        count = band_counts.get(band, 0)
        pct = round(count / corpus_count * 100, 1) if corpus_count else 0.0
        return AgentBandShare(pct=pct, count=count)

    distribution = AgentBandDistribution(
        red=share("red"), orange=share("orange"), yellow=share("yellow"), green=share("green")
    )

    pct_with_critical: float | None = None
    if gate_met and corpus_count:
        crit_runs = (
            await session.execute(
                select(func.count(func.distinct(AgentFinding.agent_run_id)))
                .select_from(AgentFinding)
                .join(AgentRun, AgentFinding.agent_run_id == AgentRun.id)
                .where(and_(base, AgentFinding.severity == "critical"))
            )
        ).scalar_one()
        pct_with_critical = round(crit_runs / corpus_count * 100, 1)

    return AgentAggregateStats(
        corpus_count=corpus_count,
        gate_target=gate_target,
        gate_met=gate_met,
        pct_with_critical=pct_with_critical,
        band_distribution=distribution,
        window_label="Whole corpus · Last 3 months",
    )
