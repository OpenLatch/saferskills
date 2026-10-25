"""Stalled-job recovery resilience (`tasks_scan._requeue_stalled_jobs`).

Regression for the worker-restart stall: the previous retrier wrapped the whole
sweep in one `try/except`, so a single `retry_job` `UniqueViolation` (a stalled
`doing` job whose `queueing_lock` a sibling `todo` already holds) aborted the
entire sweep — leaving every other orphaned cycle stuck for up to 4h and
crash-looping the retrier on `ingest_cycle_mcp_registry_lock`. The recovery must
be resilient per job AND per queue, and the boot hook must sweep every queue.
"""

from __future__ import annotations

import re
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion import procrastinate_app, tasks_scan


class _Job:
    def __init__(self, job_id: int, worker_id: int | None = None, attempts: int = 0) -> None:
        self.id = job_id
        self.worker_id = worker_id
        self.attempts = attempts


class _FakeJobManager:
    """Minimal stand-in for the Procrastinate JobManager used by the recovery."""

    def __init__(self, jobs_by_queue: dict[str, list[_Job]], fail_job_ids: set[int]) -> None:
        self._jobs = jobs_by_queue
        self._fail = fail_job_ids
        self.retried: list[int] = []
        self.finished: list[tuple[int, str]] = []
        self.listed_queues: list[str] = []

    async def get_stalled_jobs(
        self, nb_seconds: int | None = None, queue: str | None = None, **_: object
    ):
        self.listed_queues.append(queue or "")
        return list(self._jobs.get(queue or "", []))

    async def retry_job(self, job: _Job) -> None:
        if job.id in self._fail:
            # Mimic the partial-unique `queueing_lock` collision.
            raise RuntimeError('duplicate key value violates unique constraint "..._lock_idx"')
        self.retried.append(job.id)

    async def finish_job(self, job: _Job, status: Any, delete_job: bool) -> None:
        self.finished.append((job.id, status.value))


@pytest.mark.asyncio
async def test_requeue_stalled_is_resilient_to_a_per_job_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeJobManager({"scan": [_Job(1), _Job(2), _Job(3)]}, fail_job_ids={2})
    monkeypatch.setattr(procrastinate_app, "job_manager", fake)

    out = await tasks_scan._requeue_stalled_jobs(("scan",))  # pyright: ignore[reportPrivateUsage]

    # The collision on job 2 did NOT abort the sweep — 1 and 3 still re-queued.
    assert fake.retried == [1, 3]
    assert out == {"retried": 2, "skipped": 1, "failed": 0}


@pytest.mark.asyncio
async def test_stalled_duplicate_of_waiting_job_is_failed_to_release_its_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression (prod npm deadlock): an ownerless `doing` cycle whose retry hits
    the queueing-lock `UniqueViolation` (a sibling `todo` already waits) used to be
    skipped forever — still holding the shared execution `lock`, so the sibling
    could never start either. It must be FAILED so the sibling runs."""
    from procrastinate.exceptions import UniqueViolation

    class _JM(_FakeJobManager):
        async def retry_job(self, job: _Job) -> None:
            raise UniqueViolation(
                constraint_name="procrastinate_jobs_queueing_lock_idx_v1",
                queueing_lock="ingest_cycle_npm_lock",
            )

    fake = _JM({"ingest_npm": [_Job(96184)]}, fail_job_ids=set())
    monkeypatch.setattr(procrastinate_app, "job_manager", fake)

    out = await tasks_scan._requeue_stalled_jobs(("ingest_npm",))  # pyright: ignore[reportPrivateUsage]

    assert fake.finished == [(96184, "failed")]
    assert out == {"retried": 0, "skipped": 0, "failed": 1}


@pytest.mark.asyncio
async def test_poison_job_is_dead_lettered_after_max_recovery_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression (prod crash loop): a scan that wedged the loop was re-queued on
    every boot (482 attempts), killing the worker every 16 min. Past the cap it
    must be dead-lettered, not retried."""
    cap = tasks_scan._MAX_RECOVERY_ATTEMPTS  # pyright: ignore[reportPrivateUsage]
    fake = _FakeJobManager({"scan": [_Job(1, attempts=cap), _Job(2, attempts=cap - 1)]}, set())
    monkeypatch.setattr(procrastinate_app, "job_manager", fake)

    out = await tasks_scan._requeue_stalled_jobs(("scan",))  # pyright: ignore[reportPrivateUsage]

    assert fake.finished == [(1, "failed")]
    assert fake.retried == [2]
    assert out == {"retried": 1, "skipped": 0, "failed": 1}


@pytest.mark.asyncio
async def test_requeue_stalled_survives_a_per_queue_list_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _JM(_FakeJobManager):
        async def get_stalled_jobs(
            self, nb_seconds: int | None = None, queue: str | None = None, **_: object
        ):
            if queue == "ingest_github":
                raise RuntimeError("transient list failure")
            return list(self._jobs.get(queue or "", []))

    fake = _JM({"ingest_npm": [_Job(9)]}, fail_job_ids=set())
    monkeypatch.setattr(procrastinate_app, "job_manager", fake)

    out = await tasks_scan._requeue_stalled_jobs(  # pyright: ignore[reportPrivateUsage]
        ("ingest_github", "ingest_npm")
    )

    # A queue whose listing raised is skipped; the rest are still processed.
    assert fake.retried == [9]
    assert out["retried"] == 1


@pytest.mark.asyncio
async def test_boot_recovery_sweeps_every_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeJobManager({}, fail_job_ids=set())
    monkeypatch.setattr(procrastinate_app, "job_manager", fake)

    await tasks_scan.recover_orphaned_jobs_at_boot()

    # Boot recovery covers the scan queue PLUS every ingest/periodic queue.
    assert set(fake.listed_queues) == set(tasks_scan._ALL_STALLED_QUEUES)  # pyright: ignore[reportPrivateUsage]
    assert "scan" in fake.listed_queues


@pytest.mark.asyncio
@pytest.mark.parametrize("current_owner", [None, 8])
async def test_recovery_rechecks_owner_before_retry(
    monkeypatch: pytest.MonkeyPatch, current_owner: int | None
) -> None:
    class _ChangingOwner(_FakeJobManager):
        calls = 0

        async def get_stalled_jobs(
            self, nb_seconds: int | None = None, queue: str | None = None, **_: object
        ):
            self.calls += 1
            if self.calls == 1:
                return [_Job(1, worker_id=7)]
            # Either the owner resumed heartbeats (absent from abandoned jobs),
            # or a different owner now holds the job. Neither may be stolen.
            return [] if current_owner is None else [_Job(1, worker_id=current_owner)]

    fake = _ChangingOwner({}, fail_job_ids=set())
    monkeypatch.setattr(procrastinate_app, "job_manager", fake)
    assert await tasks_scan._requeue_stalled_jobs(("scan",)) == {  # pyright: ignore[reportPrivateUsage]
        "retried": 0,
        "skipped": 1,
        "failed": 0,
    }
    assert fake.retried == []


@pytest.mark.asyncio
@pytest.mark.parametrize("watchdog_seconds", [0.0, 900.0])
@pytest.mark.parametrize("entrypoint", ["boot", "periodic"])
async def test_recovery_respects_live_owner_and_configured_heartbeat_grace(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    watchdog_seconds: float,
    entrypoint: str,
) -> None:
    """Run the real JobManager SQL against PostgreSQL, isolated by a schema.

    Old jobs with live/recent owners keep their execution locks, while young
    stale-owner and ownerless jobs recover. Boot and periodic entrypoints retain this
    protection, including the minimum grace when the watchdog is disabled.
    """
    from procrastinate.manager import JobManager
    from procrastinate.schema import SchemaManager

    monkeypatch.setattr(tasks_scan.get_settings(), "worker_watchdog_timeout_s", watchdog_seconds)
    grace = max(30.0, watchdog_seconds)
    schema = f"recovery_{uuid4().hex}"
    await db_session.execute(text(f'CREATE SCHEMA "{schema}"'))
    await db_session.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
    connection = await db_session.connection()
    raw = await connection.get_raw_connection()
    driver: Any = raw.driver_connection
    await driver.execute(SchemaManager.get_schema())

    class _SessionConnector:
        async def execute_query_all_async(
            self, query: str, **parameters: Any
        ) -> list[dict[str, Any]]:
            # Adapt only the driver's parameter style; execute Procrastinate's
            # actual selection and retry SQL inside the rollback fixture.
            keys = list(parameters)
            query = re.sub(r"%\((\w+)\)s", lambda m: f"${keys.index(m[1]) + 1}", query)
            query += f" /* {schema} */"  # Keep cached enum plans scoped to this schema.
            # asyncpg infers text for the SDK's interval-string concatenation;
            # psycopg otherwise handles numeric-to-text adaptation itself.
            for key in ("nb_seconds", "seconds_since_heartbeat"):
                if key in parameters:
                    parameters[key] = str(parameters[key])
            rows: list[Any] = await driver.fetch(query, *parameters.values())
            return [dict(row) for row in rows]

        async def execute_query_async(self, query: str, **parameters: Any) -> None:
            await self.execute_query_all_async(query, **parameters)

    monkeypatch.setattr(
        procrastinate_app, "job_manager", JobManager(cast(Any, _SessionConnector()))
    )
    job_ids: dict[str, int] = {}
    for label, heartbeat_age in (
        ("live", 0),
        ("recent", grace - 1),
        ("boundary", grace),
        ("stale", grace + 1),
        ("ownerless", None),
    ):
        worker_id = None
        if heartbeat_age is not None:
            worker_id = await driver.fetchval(
                "INSERT INTO procrastinate_workers (last_heartbeat) "
                "VALUES (now() - $1 * interval '1 second') RETURNING id",
                heartbeat_age,
            )
        job_ids[label] = await driver.fetchval(
            "INSERT INTO procrastinate_jobs (queue_name, task_name, lock, worker_id) "
            "VALUES ('ingest_mcp_registry', 'ingest_cycle_mcp_registry', $1, $2) RETURNING id",
            label,
            worker_id,
        )
    await driver.execute("UPDATE procrastinate_jobs SET status = 'doing'")
    await driver.execute(
        "UPDATE procrastinate_events SET at = now() - interval '8 hours' "
        "WHERE type = 'started' AND job_id = ANY($1::bigint[])",
        [job_ids["live"], job_ids["recent"], job_ids["boundary"]],
    )

    result = (
        await tasks_scan.recover_orphaned_jobs_at_boot()
        if entrypoint == "boot"
        else await tasks_scan.ingestion_stalled_retrier(timestamp=0)
    )

    assert result == {"retried": 2, "skipped": 0, "failed": 0}
    rows: list[Any] = await driver.fetch(
        "SELECT id, status::text AS status, lock FROM procrastinate_jobs"
    )
    states = {row["id"]: (row["status"], row["lock"]) for row in rows}
    assert states == {
        job_ids["live"]: ("doing", "live"),
        job_ids["recent"]: ("doing", "recent"),
        job_ids["boundary"]: ("doing", "boundary"),
        job_ids["stale"]: ("todo", "stale"),
        job_ids["ownerless"]: ("todo", "ownerless"),
    }
