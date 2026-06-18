"""Stalled-job recovery resilience (`tasks_scan._requeue_stalled_jobs`).

Regression for the worker-restart stall: the previous retrier wrapped the whole
sweep in one `try/except`, so a single `retry_job` `UniqueViolation` (a stalled
`doing` job whose `queueing_lock` a sibling `todo` already holds) aborted the
entire sweep — leaving every other orphaned cycle stuck for up to 4h and
crash-looping the retrier on `ingest_cycle_mcp_registry_lock`. The recovery must
be resilient per job AND per queue, and the boot hook must sweep every queue.
"""

from __future__ import annotations

import pytest

from app.ingestion import procrastinate_app, tasks_scan


class _Job:
    def __init__(self, job_id: int) -> None:
        self.id = job_id


class _FakeJobManager:
    """Minimal stand-in for the Procrastinate JobManager used by the recovery."""

    def __init__(self, jobs_by_queue: dict[str, list[_Job]], fail_job_ids: set[int]) -> None:
        self._jobs = jobs_by_queue
        self._fail = fail_job_ids
        self.retried: list[int] = []
        self.listed_queues: list[str] = []

    async def get_stalled_jobs(self, nb_seconds: int, queue: str | None = None, **_: object):
        self.listed_queues.append(queue or "")
        return list(self._jobs.get(queue or "", []))

    async def retry_job(self, job: _Job) -> None:
        if job.id in self._fail:
            # Mimic the partial-unique `queueing_lock` collision.
            raise RuntimeError('duplicate key value violates unique constraint "..._lock_idx"')
        self.retried.append(job.id)


@pytest.mark.asyncio
async def test_requeue_stalled_is_resilient_to_a_per_job_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeJobManager({"scan": [_Job(1), _Job(2), _Job(3)]}, fail_job_ids={2})
    monkeypatch.setattr(procrastinate_app, "job_manager", fake)

    out = await tasks_scan._requeue_stalled_jobs(("scan",), 0)  # pyright: ignore[reportPrivateUsage]

    # The collision on job 2 did NOT abort the sweep — 1 and 3 still re-queued.
    assert fake.retried == [1, 3]
    assert out == {"retried": 2, "skipped": 1}


@pytest.mark.asyncio
async def test_requeue_stalled_survives_a_per_queue_list_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _JM(_FakeJobManager):
        async def get_stalled_jobs(self, nb_seconds: int, queue: str | None = None, **_: object):
            if queue == "ingest_github":
                raise RuntimeError("transient list failure")
            return list(self._jobs.get(queue or "", []))

    fake = _JM({"ingest_npm": [_Job(9)]}, fail_job_ids=set())
    monkeypatch.setattr(procrastinate_app, "job_manager", fake)

    out = await tasks_scan._requeue_stalled_jobs(  # pyright: ignore[reportPrivateUsage]
        ("ingest_github", "ingest_npm"), 0
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
