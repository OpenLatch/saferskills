"""Procrastinate JobManager whose job-status write-back survives a DB blip.

When a job ends, Procrastinate persists its outcome with ONE `finish_job` /
`retry_job` query and no retry. If that query hits a dropped connection (a
Postgres restart / Fly-proxy recycle), the job task still exits and leaves the
worker's in-memory running set, but its row stays `doing` under the *live*
worker id. The owner's heartbeat stays fresh, so heartbeat-based stalled
recovery never selects it, and its execution `lock` blocks every later cycle of
the source forever (prod mcp_registry, Oct 2026: zombie `doing` for 15h after a
17:51 connection drop while the worker was otherwise healthy).

Retrying only connection-level failures (`psycopg.OperationalError`, incl.
`PoolTimeout`) over ~2 min closes the gap: an outage longer than that also fails
the worker's 10 s heartbeat, which self-stops the worker, and the supervisor
restarts it under a new id. The old id then goes stale, and the existing stalled
recovery picks the job up. A replayed write whose first attempt had committed
fails with Procrastinate's "not in doing status" `RaiseException`, which is not
an OperationalError. It is raised, not retried.
"""

from __future__ import annotations

import asyncio
from typing import Any

import psycopg
import structlog
from procrastinate.exceptions import ConnectorException
from procrastinate.manager import JobManager

logger = structlog.get_logger(__name__)

STATUS_WRITE_RETRY_DELAYS_S: tuple[float, ...] = (1.0, 2.0, 5.0, 15.0, 30.0, 60.0)


def _is_connection_error(exc: ConnectorException) -> bool:
    return isinstance(exc.__cause__, psycopg.OperationalError)


class ResilientJobManager(JobManager):
    async def _with_retry(self, op: str, job_id: int, call: Any) -> None:
        for delay in (*STATUS_WRITE_RETRY_DELAYS_S, None):
            try:
                return await call()
            except ConnectorException as exc:
                if delay is None or not _is_connection_error(exc):
                    raise
                logger.warning(
                    "procrastinate.status_write_retry",
                    op=op,
                    job_id=job_id,
                    delay_s=delay,
                    error=str(exc.__cause__)[:160],
                )
            await asyncio.sleep(delay)

    async def finish_job_by_id_async(self, job_id: int, *args: Any, **kwargs: Any) -> None:
        parent = super().finish_job_by_id_async
        await self._with_retry("finish_job", job_id, lambda: parent(job_id, *args, **kwargs))

    async def retry_job_by_id_async(self, job_id: int, *args: Any, **kwargs: Any) -> None:
        parent = super().retry_job_by_id_async
        await self._with_retry("retry_job", job_id, lambda: parent(job_id, *args, **kwargs))
