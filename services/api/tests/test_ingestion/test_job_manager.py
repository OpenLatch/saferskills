"""Job-status write-back survives a dropped DB connection (`app.ingestion.job_manager`).

Regression for the prod mcp_registry zombie (Oct 2026): a connection drop made
Procrastinate's single end-of-job `finish_job`/`retry_job` write fail, leaving the
row `doing` under a live worker forever — heartbeat recovery never reclaims it,
and its `lock` blocked every later cycle.
"""

from __future__ import annotations

from typing import Any, cast

import psycopg
import pytest
from procrastinate.exceptions import ConnectorException
from procrastinate.jobs import Status

from app.ingestion import job_manager, procrastinate_app


def _wrapped(cause: Exception) -> ConnectorException:
    try:
        raise ConnectorException() from cause
    except ConnectorException as exc:
        return exc


class _FlakyConnector:
    def __init__(self, failures: list[Exception]) -> None:
        self._failures = failures
        self.queries: list[str] = []

    async def execute_query_async(self, query: str, **_: Any) -> None:
        self.queries.append(query)
        if self._failures:
            raise self._failures.pop(0)


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []

    async def _sleep(delay: float) -> None:
        slept.append(delay)

    monkeypatch.setattr(job_manager.asyncio, "sleep", _sleep)
    return slept


def _app_manager_with(connector: _FlakyConnector) -> Any:
    jm = procrastinate_app.job_manager
    return type(jm)(connector=cast(Any, connector))


async def test_finish_job_retries_a_dropped_connection(no_sleep: list[float]) -> None:
    conn = _FlakyConnector([_wrapped(psycopg.OperationalError("connection closed"))] * 2)
    jm = _app_manager_with(conn)

    await jm.finish_job_by_id_async(job_id=7, status=Status.FAILED, delete_job=False)

    assert len(conn.queries) == 3
    assert no_sleep == [1.0, 2.0]


async def test_retry_job_retries_a_dropped_connection(no_sleep: list[float]) -> None:
    from procrastinate import utils

    conn = _FlakyConnector([_wrapped(psycopg.OperationalError("server closed"))])
    jm = _app_manager_with(conn)

    await jm.retry_job_by_id_async(job_id=7, retry_at=utils.utcnow())

    assert len(conn.queries) == 2


async def test_non_connection_error_is_not_retried(no_sleep: list[float]) -> None:
    # e.g. a replayed write whose first attempt committed: "not in doing status".
    conn = _FlakyConnector([_wrapped(psycopg.errors.RaiseException("not in doing status"))])
    jm = _app_manager_with(conn)

    with pytest.raises(ConnectorException):
        await jm.finish_job_by_id_async(job_id=7, status=Status.SUCCEEDED, delete_job=False)

    assert len(conn.queries) == 1
    assert no_sleep == []


async def test_gives_up_after_the_retry_window(no_sleep: list[float]) -> None:
    attempts = len(job_manager.STATUS_WRITE_RETRY_DELAYS_S) + 1
    conn = _FlakyConnector([_wrapped(psycopg.OperationalError("down"))] * attempts)
    jm = _app_manager_with(conn)

    with pytest.raises(ConnectorException):
        await jm.finish_job_by_id_async(job_id=7, status=Status.FAILED, delete_job=False)

    assert len(conn.queries) == attempts
    assert no_sleep == list(job_manager.STATUS_WRITE_RETRY_DELAYS_S)
