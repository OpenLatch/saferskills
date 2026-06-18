"""Durable auto-scan pipeline — every indexed public-github capability is scanned.

This replaces the popularity-gated `auto_scan_trigger_deep/_lite` fire-and-forget
triggers (which on a fresh DB never ran). Three pieces, all in the in-process
Procrastinate worker (advisory lock 0x5AFE5C13):

1. `scan_capability_repo` (queue=`scan`) — the durable per-repo scan JOB. Retry +
   stalled-recovery + `queueing_lock`/`lock` dedup are what make the bulk path
   crash-safe (vs the interactive POST /scans path, which stays
   `asyncio.create_task`). It conditionally resolves the repo ref (304 = free),
   then: unchanged content + current versions → skip (bump `last_checked_at`);
   rubric/engine bump only → re-evaluate from STORED bytes (no GitHub re-crawl);
   content changed / never scanned → full fetch + scan. Idempotent on
   (github_url, ref_sha, rubric_version).

2. `auto_scan_reconcile` (periodic, every 10 min) — the coverage + versioned
   re-eval + freshness drainer. Selects public-github high/medium not-archived
   repos that are unscanned / stale-version / stale-freshness, popularity-first,
   bounded by `SCAN_RECONCILE_BATCH`, and defers a scan job per repo (the
   `queueing_lock` dedups against in-flight jobs).

3. `scan_stalled_retrier` (periodic, every 15 min) — re-queues `scan`-queue jobs
   the worker abandoned on a restart (Procrastinate's documented stalled-job
   recovery).

Concurrency is bounded by `SCAN_MAX_CONCURRENCY` via an in-body semaphore; the
boot-time `assert_worker_concurrency_budget` guarantees
INGESTION_WORKER_CONCURRENCY + SCAN_MAX_CONCURRENCY < the SQLAlchemy pool.

`run_reconcile` / `execute_scan` are the testable session-taking entry points
(the deferrer is injected so tests assert selection + decisions without spawning
real scans).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.memory import rss_mb
from app.ingestion import PERIODIC_MAINTENANCE_PRIORITY, procrastinate_app
from app.ingestion.framework.failure import classify_failure, is_transient_failure
from app.models.repo_fetch_state import RepoFetchState
from app.models.scan import Scan
from app.models.scan_run import ScanRun
from app.scan import engine, fetch, persistence
from app.scan.fetch import FetchError, ResolvedRef, TarballTooLargeError
from app.services.artifact_bytes import resolve_snapshot

logger = structlog.get_logger(__name__)

# Re-queue scan-queue jobs whose worker died and left them `doing` past this.
_STALLED_SECONDS = 1800  # 30 min — comfortably above a slow single-repo scan.

DeferFn = Callable[[str], Awaitable[bool]]

# In-body concurrency cap for durable scan jobs (the cleanest Procrastinate
# mechanism for a single in-process worker — bounds `scan`-queue work without a
# separate worker). Lazily bound to the running loop on first use.
_scan_sem: asyncio.Semaphore | None = None


def _semaphore() -> asyncio.Semaphore:
    global _scan_sem
    if _scan_sem is None:
        _scan_sem = asyncio.Semaphore(get_settings().scan_max_concurrency)
    return _scan_sem


def _versions(settings: Any) -> tuple[str, str]:
    rubric = settings.rubric_version or settings.git_sha or "unknown"
    engine_v = settings.engine_version or settings.git_sha or "unknown"
    return rubric, engine_v


# ── fetch-state + stamp helpers ───────────────────────────────────────────


async def _upsert_fetch_state(
    session: AsyncSession,
    github_url: str,
    *,
    etag: str | None,
    last_modified: str | None,
    ref_sha: str | None,
) -> None:
    now = datetime.now(UTC)
    stmt = (
        pg_insert(RepoFetchState)
        .values(
            github_url=github_url,
            etag=etag,
            last_modified=last_modified,
            resolved_ref_sha=ref_sha,
            last_checked_at=now,
        )
        .on_conflict_do_update(
            index_elements=["github_url"],
            set_={
                "etag": etag,
                "last_modified": last_modified,
                "resolved_ref_sha": ref_sha,
                "last_checked_at": now,
                "updated_at": now,
            },
        )
    )
    await session.execute(stmt)


# A repo's public-github capability rows (they share the URL + move together).
# Bound-param `:url` keeps it injection-safe; the literal fragment is shared so the
# three queries below can't drift apart.
_REPO_PUBLIC_GITHUB = "github_url = :url AND source_kind = 'github' AND visibility = 'public'"

_STAMP_SCANNED = text(f"""
    UPDATE catalog_items
    SET last_scanned_at = now(),
        scanned_rubric_version = :rv,
        scanned_engine_version = :ev,
        last_checked_at = now(),
        updated_at = now()
    WHERE {_REPO_PUBLIC_GITHUB}
""")

_BUMP_CHECKED = text(f"""
    UPDATE catalog_items
    SET last_checked_at = now()
    WHERE {_REPO_PUBLIC_GITHUB}
""")

_REPO_STAMP = text(f"""
    SELECT last_scanned_at, scanned_rubric_version, scanned_engine_version
    FROM catalog_items
    WHERE {_REPO_PUBLIC_GITHUB}
    ORDER BY last_scanned_at DESC NULLS LAST
    LIMIT 1
""")


async def _stamp_scanned(
    session: AsyncSession, github_url: str, rubric: str, engine_v: str
) -> None:
    """Stamp the queue-of-record recency columns on every public-github cap of the repo."""
    await session.execute(_STAMP_SCANNED, {"rv": rubric, "ev": engine_v, "url": github_url})


async def _load_repo_file_index(session: AsyncSession, github_url: str) -> list[tuple[str, bytes]]:
    """Reconstruct a repo file index from the STORED snapshots of its latest run.

    Re-eval-from-bytes (rule/engine bump, content unchanged): union every
    capability scan's stored text bytes (deduped by path) into one in-memory
    index the engine re-discovers + re-scores with NO GitHub fetch. Returns []
    when nothing is stored (caller falls back to a fresh fetch)."""
    run = (
        await session.execute(
            select(ScanRun)
            .where(
                ScanRun.github_url == github_url,
                ScanRun.status == "completed",
                ScanRun.source_kind == "github",
            )
            .order_by(ScanRun.scanned_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if run is None:
        return []
    scans = (await session.execute(select(Scan).where(Scan.scan_run_id == run.id))).scalars().all()
    merged: dict[str, bytes] = {}
    for scan in scans:
        snapshot = await resolve_snapshot(session, scan)
        for path, content in snapshot.items():
            if content is not None and path not in merged:
                merged[path] = content
    return list(merged.items())


# ── the three scan paths ──────────────────────────────────────────────────


async def _full_scan(
    github_url: str, rubric: str, engine_v: str, resolved: ResolvedRef, *, reason: str
) -> str:
    """Fetch the repo fresh, run the engine, persist + stamp (content change / new).

    Returns the action taken: `"scan"` on success, `"error"` on a PERMANENT fetch
    failure. A `FetchError` from `run_repo_scan` (oversized tarball past the
    anti-DOS cap, repo deleted mid-window, invalid ref) is deterministic — a retry
    re-downloads for the same failure — so it must NOT bubble out of the durable
    job (that would burn 3 retries then dead-letter, re-fetching the whole repo
    each time). Instead we mark the run `failed` and stamp the recency columns so
    the drainer throttles the repo to the freshness cadence (an occasional re-check
    in case it later shrinks) rather than re-selecting it every tick. Transient
    failures (5xx / timeout) surface as httpx errors, not `FetchError`, so they
    still propagate and retry.

    **Size-gated hybrid fetch.** A repo whose reported size exceeds
    `scan_large_repo_size_kb` skips the tarball and uses the Git Trees + raw path
    (`run_repo_scan_via_trees`) — same engine, same fileset (every blob ≤ 5 MiB),
    no 25 MiB single-stream cap. Because `size` is approximate, a repo that
    *looks* small but blows the cap raises `TarballTooLargeError` (a `FetchError`
    subclass) — caught here for a one-shot fallback to the trees path before the
    permanent-failure handling. A truncated tree / deleted repo / invalid ref
    stays a plain `FetchError` → marked failed (today's behaviour, unchanged).
    """
    from app.db.session import AsyncSessionLocal

    settings = get_settings()
    ref_sha = resolved.ref_sha or "0" * 40
    idempotency_key = persistence.compute_idempotency_key(
        github_url, ref_sha=ref_sha, rubric_version=rubric
    )
    async with AsyncSessionLocal() as session:
        run = await persistence.persist_pending_scan_run(
            session,
            idempotency_key=idempotency_key,
            github_url=github_url,
            rubric_version=rubric,
            engine_version=engine_v,
            source="ingestion",
            visibility="public",
            source_kind="github",
        )
        await session.commit()
        run_id = run.id

    # Network + CPU OUTSIDE any DB session (don't hold a pooled connection).
    default_branch = resolved.default_branch or "main"
    is_large = resolved.size_kb is not None and resolved.size_kb > settings.scan_large_repo_size_kb
    try:
        if is_large:
            repo = await engine.run_repo_scan_via_trees(
                github_url, rubric, ref_sha=ref_sha, default_branch=default_branch
            )
        else:
            try:
                repo = await engine.run_repo_scan(github_url, rubric)
            except TarballTooLargeError:
                # `size` is approximate — a repo that looked small blew the 25 MiB
                # cap. Retry once via the trees path before giving up.
                logger.info(
                    "scan_capability_repo.tarball_oversize_fallback",
                    github_url=github_url,
                    reason=reason,
                )
                repo = await engine.run_repo_scan_via_trees(
                    github_url, rubric, ref_sha=ref_sha, default_branch=default_branch
                )
    except FetchError as exc:
        async with AsyncSessionLocal() as session:
            run = await session.get(ScanRun, run_id)
            if run is not None:
                run.status = "failed"
            # Stamp recency (not just last_checked_at) so a never-scanned repo
            # leaves the `last_scanned_at IS NULL` coverage selection — the failed
            # scan_runs row is the honest record; the drainer re-checks on the
            # freshness window, not every 10 min.
            await _stamp_scanned(session, github_url, rubric, engine_v)
            await session.commit()
        logger.info(
            "scan_capability_repo.fetch_failed",
            github_url=github_url,
            reason=reason,
            error=str(exc),
        )
        return "error"

    async with AsyncSessionLocal() as session:
        run = await session.get(ScanRun, run_id)
        if run is not None:
            await persistence.persist_completed_scan_run(session, run, repo)
        await _stamp_scanned(session, github_url, rubric, engine_v)
        await _upsert_fetch_state(
            session,
            github_url,
            etag=resolved.etag,
            last_modified=resolved.last_modified,
            ref_sha=repo.ref_sha,
        )
        await session.commit()
    return "scan"


async def _reeval_from_bytes(
    github_url: str, rubric: str, engine_v: str, *, ref_sha: str | None, resolved: ResolvedRef
) -> bool:
    """Re-score the repo from STORED bytes (rule/engine bump, no GitHub fetch).

    Returns False when no stored bytes can be reconstructed (caller fetches)."""
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        file_index = await _load_repo_file_index(session, github_url)
    if not file_index:
        return False

    content_ref = ref_sha or "0" * 40
    repo = engine.run_repo_scan_from_index(file_index, rubric, ref_sha=content_ref)

    idempotency_key = persistence.compute_idempotency_key(
        github_url, ref_sha=content_ref, rubric_version=rubric
    )
    async with AsyncSessionLocal() as session:
        run = await persistence.persist_pending_scan_run(
            session,
            idempotency_key=idempotency_key,
            github_url=github_url,
            rubric_version=rubric,
            engine_version=engine_v,
            source="rescan_rules",
            visibility="public",
            source_kind="github",
        )
        await persistence.persist_completed_scan_run(session, run, repo)
        await _stamp_scanned(session, github_url, rubric, engine_v)
        await _upsert_fetch_state(
            session,
            github_url,
            etag=resolved.etag,
            last_modified=resolved.last_modified,
            ref_sha=content_ref,
        )
        await session.commit()
    return True


def decide_scan_action(*, ref_unchanged: bool, versions_current: bool, has_prior_scan: bool) -> str:
    """Pure change-gate decision: `skip` | `reeval` | `scan`.

    - unchanged ref + current rubric+engine → `skip` (cheap last_checked_at bump).
    - unchanged ref + stale versions + a prior scan → `reeval` from stored bytes.
    - else (content changed / never scanned) → full `scan` (fetch).
    """
    if ref_unchanged and versions_current:
        return "skip"
    if ref_unchanged and not versions_current and has_prior_scan:
        return "reeval"
    return "scan"


async def execute_scan(github_url: str, *, reason: str = "reconcile") -> dict[str, str]:
    """Decide skip / re-eval-from-bytes / full-fetch for one repo, then run it.

    The durable job body. Conditional ref resolve gates everything:
    - 304 / unchanged ref + current rubric+engine → skip (cheap `last_checked_at` bump).
    - unchanged ref + stale versions + stored bytes → re-eval from bytes (no fetch).
    - else (content changed / never scanned / no stored bytes) → full fetch + scan.
    """
    from app.db.session import AsyncSessionLocal

    settings = get_settings()
    rubric, engine_v = _versions(settings)

    async with AsyncSessionLocal() as session:
        state = await session.get(RepoFetchState, github_url)
        prior_etag = state.etag if state else None
        prior_lm = state.last_modified if state else None
        prior_sha = state.resolved_ref_sha if state else None
        stamp = (await session.execute(_REPO_STAMP, {"url": github_url})).one_or_none()

    try:
        resolved = await fetch.resolve_ref(github_url, etag=prior_etag, last_modified=prior_lm)
    except FetchError:
        # Deleted / invalid repo — a PERMANENT 404 / bad ref (a transient blip raises
        # an httpx error that propagates to the retrier, not FetchError). Stamp the
        # recency columns (not just last_checked_at): a never-scanned repo whose URL
        # 404s stays `last_scanned_at IS NULL`, so a bare last_checked_at bump leaves
        # it in the coverage selection and reconcile re-selects + re-resolves it EVERY
        # tick — endless `unresolvable` log spam + wasted GitHub budget. Stamping
        # recency drops it from coverage; archive_check owns the eventual 404-timeline
        # → archived flip. Mirrors `_full_scan`'s FetchError handling.
        async with AsyncSessionLocal() as session:
            await _stamp_scanned(session, github_url, rubric, engine_v)
            await session.commit()
        logger.info("scan_capability_repo.unresolvable", github_url=github_url, reason=reason)
        return {"action": "error", "reason": reason}

    ref_unchanged = resolved.not_modified or (
        resolved.ref_sha is not None and prior_sha is not None and resolved.ref_sha == prior_sha
    )
    has_prior_scan = stamp is not None and stamp.last_scanned_at is not None
    versions_current = (
        stamp is not None
        and stamp.last_scanned_at is not None
        and stamp.scanned_rubric_version == rubric
        and stamp.scanned_engine_version == engine_v
    )
    action = decide_scan_action(
        ref_unchanged=ref_unchanged,
        versions_current=versions_current,
        has_prior_scan=has_prior_scan,
    )

    if action == "skip":
        async with AsyncSessionLocal() as session:
            await session.execute(_BUMP_CHECKED, {"url": github_url})
            await _upsert_fetch_state(
                session,
                github_url,
                etag=resolved.etag,
                last_modified=resolved.last_modified,
                ref_sha=resolved.ref_sha or prior_sha,
            )
            await session.commit()
        return {"action": "skip", "reason": reason}

    if action == "reeval":
        did = await _reeval_from_bytes(
            github_url, rubric, engine_v, ref_sha=prior_sha, resolved=resolved
        )
        if did:
            return {"action": "reeval", "reason": reason}
        # No reconstructable bytes — fall through to a fresh fetch.

    action = await _full_scan(github_url, rubric, engine_v, resolved, reason=reason)
    return {"action": action, "reason": reason}


# ── Procrastinate tasks ────────────────────────────────────────────────────


async def _mark_repo_pending_runs_failed(github_url: str) -> None:
    """Best-effort: flip this repo's non-terminal (`pending`/`running`) scan_runs to
    `failed` so a permanent error doesn't leave an orphan lingering until the 15-min
    stale-run recovery. Scoped to the repo whose scan just failed; the per-repo
    `lock=scan:<url>` guarantees no OTHER scan of this URL is concurrently in-flight,
    so this never races a legitimate run. Swallows its own errors (it is cleanup)."""
    from app.db.session import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(ScanRun)
                .where(
                    ScanRun.github_url == github_url,
                    ScanRun.status.in_(("pending", "running")),
                )
                .values(status="failed")
            )
            await session.commit()
    except Exception:
        logger.debug("scan_capability_repo.mark_failed_skipped", github_url=github_url)


@procrastinate_app.task(name="scan_capability_repo", queue="scan", retry=3)
async def scan_capability_repo(github_url: str, reason: str = "reconcile") -> dict[str, str]:
    """Durable per-repo scan job (bounded by SCAN_MAX_CONCURRENCY).

    Robustness: `execute_scan` cleanly handles `FetchError` (the
    deterministic fetch-failure class). But `resolve_ref` raises a raw
    `httpx.HTTPStatusError` on a 403/429/5xx — NOT a `FetchError` — and a
    shape-drift bug in persistence raises `KeyError`/`ValueError`. Without this
    wrapper either bubbles out as an unhandled traceback and burns the 3 retries
    (transient) or 3 retries + 3 tracebacks (permanent). So: classify, emit ONE
    clean WARN, mark the pending run failed, and re-raise ONLY when transient (a
    genuine blip Procrastinate should retry). Permanent errors are swallowed —
    retrying a deterministic bug just re-fails.
    """
    async with _semaphore():
        try:
            result = await execute_scan(github_url, reason=reason)
            logger.info(
                "memory.rss_mb",
                rss_mb=rss_mb(),
                context="scan_job",
                github_url=github_url,
                action=result.get("action"),
            )
            return result
        except Exception as exc:
            reason_enum = classify_failure(exc)
            await _mark_repo_pending_runs_failed(github_url)
            if is_transient_failure(exc):
                logger.warning(
                    "scan_capability_repo.transient_failure",
                    github_url=github_url,
                    reason=reason_enum,
                    error_class=type(exc).__name__,
                    error=str(exc)[:300],
                )
                raise  # genuine blip — let Procrastinate's retry=3 take it
            logger.warning(
                "scan_capability_repo.permanent_failure",
                github_url=github_url,
                reason=reason_enum,
                error_class=type(exc).__name__,
                error=str(exc)[:300],
            )
            return {"action": "error", "reason": reason}


async def defer_scan_job(github_url: str, reason: str = "reconcile") -> bool:
    """Best-effort defer of a `scan_capability_repo` job, deduped per repo URL.

    `queueing_lock` makes a second enqueue while one is already queued a no-op
    (the drainer + the merger on-ingest hook can't double-enqueue); `lock`
    prevents two scans of the same repo running concurrently. Returns False when
    a job is already enqueued (or on any defer error — never breaks the caller).

    The `queueing_lock` pre-check is load-bearing for log hygiene, not just speed:
    Procrastinate's batch defer (`procrastinate_defer_jobs_v1`) does a plain INSERT
    and lets the partial-unique-index violation raise `AlreadyEnqueued`. Postgres
    logs every such failed INSERT as an ERROR even though we catch it — so during a
    full-feed crawl the merger on-ingest hook re-deferring thousands of
    already-queued repos floods the DB log. Checking the lock first keeps the
    steady-state path INSERT-free; the `AlreadyEnqueued` catch stays as the race
    backstop.

    The check covers `doing` as well as `todo`: the `queueing_lock` partial unique
    index only blocks a second `todo`, so a fresh enqueue is allowed *while one is
    running*. Then when the running job fails and Procrastinate retries it
    (`procrastinate_retry_job_v2` flips it back to `todo`), it collides with that
    sibling `todo` on the index → `duplicate key … queueing_lock_idx_v1` ERROR in
    the DB log. Skipping the enqueue while a job is `doing` prevents the sibling
    from ever being created (the 10-min drainer re-selects the repo if it still
    needs a scan, so freshness is preserved).
    """
    if not github_url:
        return False
    lock = f"scan:{github_url}"
    try:
        from procrastinate.exceptions import AlreadyEnqueued

        existing = await procrastinate_app.job_manager.list_jobs_async(queueing_lock=lock)
        if any(j.status in ("todo", "doing") for j in existing):
            return False

        try:
            await scan_capability_repo.configure(
                queueing_lock=lock,
                lock=lock,
            ).defer_async(github_url=github_url, reason=reason)
            return True
        except AlreadyEnqueued:
            return False
    except Exception:
        logger.debug("defer_scan_job.skipped", github_url=github_url)
        return False


_RECONCILE_SELECT = text("""
    SELECT github_url, MAX(popularity_score) AS pop
    FROM catalog_items
    WHERE source_kind = 'github' AND visibility = 'public'
      AND archived = false
      AND github_url IS NOT NULL
      AND (
          last_scanned_at IS NULL
          OR scanned_rubric_version IS DISTINCT FROM :rubric
          OR scanned_engine_version IS DISTINCT FROM :engine
          OR last_checked_at IS NULL
          OR last_checked_at < now() - make_interval(days => :freshness)
      )
    GROUP BY github_url
    ORDER BY pop DESC
    LIMIT :limit
""")


async def run_reconcile(session: AsyncSession, *, defer: DeferFn) -> int:
    """Select stale repos (coverage / version-bump / freshness), popularity-first,
    and defer a scan job per repo. Returns the count enqueued (deduped)."""
    settings = get_settings()
    rubric, engine_v = _versions(settings)
    rows = (
        await session.execute(
            _RECONCILE_SELECT,
            {
                "rubric": rubric,
                "engine": engine_v,
                "freshness": settings.scan_freshness_days,
                "limit": settings.scan_reconcile_batch,
            },
        )
    ).all()
    enqueued = 0
    for r in rows:
        if await defer(r.github_url):
            enqueued += 1
    return enqueued


@procrastinate_app.periodic(cron="*/10 * * * *")
@procrastinate_app.task(
    name="auto_scan_reconcile",
    queue="periodic",
    queueing_lock="auto_scan_reconcile_lock",
    priority=PERIODIC_MAINTENANCE_PRIORITY,
)
async def auto_scan_reconcile(timestamp: int) -> dict[str, Any]:
    settings = get_settings()
    if not settings.scan_autoscan_enabled:
        return {"enqueued": 0, "skipped": "disabled"}
    from app.db.session import AsyncSessionLocal

    # A failing reconcile tick must emit a clean error log, NOT a raw traceback
    # — the drainer is periodic, so the next 10-min tick recovers. Without
    # this the periodic task re-raises and Procrastinate dumps a full stack trace.
    try:
        async with AsyncSessionLocal() as session:
            enqueued = await run_reconcile(session, defer=defer_scan_job)
    except Exception as exc:
        logger.error(
            "auto_scan_reconcile.failed",
            error_class=type(exc).__name__,
            error=str(exc)[:300],
        )
        return {"enqueued": 0, "error": type(exc).__name__}
    logger.info("auto_scan_reconcile.done", enqueued=enqueued)
    return {"enqueued": enqueued}


# The ingest + periodic-maintenance queues `scan_stalled_retrier` does NOT cover.
# A worker restart orphaned a `doing` cycle on one of these forever (the known
# ~1-orphaned-cycle/hour leak), since the scan retrier is `queue="scan"` only.
_INGEST_QUEUES = (
    "ingest_github",
    "ingest_aggregator",
    "ingest_mcp_registry",
    "ingest_npm",
    "ingest_pypi",
    "periodic",
)
# Every queue a stalled `doing` job can live on — the boot-time recovery sweeps all.
_ALL_STALLED_QUEUES = ("scan", *_INGEST_QUEUES)


async def _requeue_stalled_jobs(queues: tuple[str, ...], nb_seconds: int) -> dict[str, int]:
    """Re-queue `doing` jobs a dead worker abandoned, across `queues`.

    Resilient PER JOB and PER QUEUE: a single `retry_job` failure — notably the
    `queueing_lock` partial-unique `UniqueViolation`, raised when a stalled job's
    lock is already held by a sibling `todo` (the stalled one is a duplicate) — must
    NOT abort the whole sweep. The previous loop wrapped every queue + every job in
    one `try/except`, so one collision on `ingest_cycle_mcp_registry_lock` left every
    OTHER stalled job orphaned and crash-looped the retrier. A
    skipped duplicate self-heals on a later tick once the sibling frees the slot.
    """
    jm = procrastinate_app.job_manager
    retried = 0
    skipped = 0
    for queue in queues:
        try:
            stalled = await jm.get_stalled_jobs(nb_seconds=nb_seconds, queue=queue)
        except Exception:
            logger.exception("requeue_stalled.list_failed", queue=queue)
            continue
        for job in stalled:
            try:
                await jm.retry_job(job)
                retried += 1
            except Exception as exc:
                skipped += 1
                logger.warning(
                    "requeue_stalled.retry_skipped",
                    queue=queue,
                    job_id=getattr(job, "id", None),
                    error=str(exc)[:160],
                )
    if retried or skipped:
        logger.info("requeue_stalled.done", retried=retried, skipped=skipped)
    return {"retried": retried, "skipped": skipped}


async def recover_orphaned_jobs_at_boot() -> dict[str, int]:
    """Boot-time recovery of orphaned `doing` Procrastinate jobs (called from
    `app.worker_main`, after the connector opens, before the supervisor starts).

    At worker boot the *previous* worker process is gone, so EVERY `doing` job is an
    orphan whose `queueing_lock` blocks fresh cycles. `nb_seconds=0` selects them all
    and re-queues them immediately. Without this, an orphan left by a deploy/restart
    blocked its source for up to `ingestion_stalled_seconds` (4h) — which is what
    stalled staging ingestion after each worker redeploy (the lock on
    `ingest_cycle_mcp_registry` was held by the cycle the restart abandoned). The
    periodic `*_stalled_retrier`s remain the steady-state net for mid-run restarts.
    """
    return await _requeue_stalled_jobs(_ALL_STALLED_QUEUES, 0)


@procrastinate_app.periodic(cron="*/15 * * * *")
@procrastinate_app.task(
    name="scan_stalled_retrier",
    queue="periodic",
    queueing_lock="scan_stalled_retrier_lock",
    priority=PERIODIC_MAINTENANCE_PRIORITY,
)
async def scan_stalled_retrier(timestamp: int) -> dict[str, int]:
    """Re-queue `scan`-queue jobs the worker abandoned on a restart (durability)."""
    return await _requeue_stalled_jobs(("scan",), _STALLED_SECONDS)


@procrastinate_app.periodic(cron="*/15 * * * *")
@procrastinate_app.task(
    name="ingestion_stalled_retrier",
    queue="periodic",
    queueing_lock="ingestion_stalled_retrier_lock",
    priority=PERIODIC_MAINTENANCE_PRIORITY,
)
async def ingestion_stalled_retrier(timestamp: int) -> dict[str, int]:
    """Re-queue ingest-queue (+ `periodic`) jobs a worker abandoned on a restart.

    Sibling to `scan_stalled_retrier` (which is `queue="scan"` only). Uses a generous
    `ingestion_stalled_seconds` (default 4h) so a legitimately-long in-flight crawl
    (mcp_registry full feed) is never re-queued out from under itself. Immediate
    post-restart recovery is handled separately by `recover_orphaned_jobs_at_boot`.
    """
    return await _requeue_stalled_jobs(_INGEST_QUEUES, get_settings().ingestion_stalled_seconds)
