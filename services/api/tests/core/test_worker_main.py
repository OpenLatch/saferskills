"""Tests for the standalone worker entrypoint (app/worker_main.py)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.startup_state import startup_state


def _patch_boot(
    monkeypatch: pytest.MonkeyPatch, *, healthy: bool, order: list[str]
) -> dict[str, Any]:
    """Patch every external touchpoint of worker_main.main(); record call order."""
    import app.ingestion as ingestion_mod
    import app.ingestion.tasks as tasks_mod
    import app.ingestion.worker as worker_mod
    import app.queue.scan_runner as scan_runner_mod
    import app.worker_main as wm

    def rec(name: str, *, ret: Any = None, sync: bool = False) -> Any:
        if sync:

            def _s(*_a: object, **_k: object) -> Any:
                order.append(name)
                return ret

            return MagicMock(side_effect=_s)

        async def _a(*_a: object, **_k: object) -> Any:
            order.append(name)
            return ret

        return AsyncMock(side_effect=_a)

    async def _run_startup(*_a: object, **_k: object) -> None:
        order.append("run_startup")
        if healthy:
            startup_state.mark_migrations_ok()
        else:
            startup_state.mark_migrations_failed("no db")

    monkeypatch.setattr(wm, "init_observability", rec("init_observability"))
    monkeypatch.setattr(wm, "run_startup", _run_startup)
    monkeypatch.setattr(wm, "init_pool", rec("init_pool"))
    monkeypatch.setattr(wm, "close_pool", rec("close_pool"))
    monkeypatch.setattr(wm, "shutdown_observability", rec("shutdown_observability", sync=True))
    monkeypatch.setattr(scan_runner_mod, "recover_stale_scans", rec("recover_stale_scans"))
    monkeypatch.setattr(
        tasks_mod, "recover_stale_ingestion_runs", rec("recover_stale_ingestion_runs")
    )

    open_async = rec("open_async")
    close_async = AsyncMock()
    apply_schema = rec("apply_schema")
    budget = rec("budget", sync=True)

    def _start_supervisor(*_a: object, **_k: object) -> Any:
        return _supervisor_coro(order)

    supervisor = MagicMock(side_effect=_start_supervisor)
    monkeypatch.setattr(ingestion_mod.procrastinate_app, "open_async", open_async)
    monkeypatch.setattr(ingestion_mod.procrastinate_app, "close_async", close_async)
    monkeypatch.setattr(worker_mod, "apply_procrastinate_schema_locked", apply_schema)
    monkeypatch.setattr(worker_mod, "assert_worker_concurrency_budget", budget)
    monkeypatch.setattr(worker_mod, "ingestion_worker_supervisor", supervisor)

    return {
        "open_async": open_async,
        "apply_schema": apply_schema,
        "supervisor": supervisor,
        "budget": budget,
        "close_async": close_async,
    }


async def _supervisor_coro(order: list[str]) -> None:
    order.append("supervisor")  # returns immediately → main() proceeds to teardown


@pytest.fixture(autouse=True)
def _reset_startup_state() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    prev_ok = startup_state.migrations_ok
    prev_err = startup_state.migrations_error
    yield
    startup_state.migrations_ok = prev_ok
    startup_state.migrations_error = prev_err


@pytest.mark.asyncio
async def test_boot_sequence_order(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.worker_main as wm

    order: list[str] = []
    mocks = _patch_boot(monkeypatch, healthy=True, order=order)

    rc = await wm.main()

    assert rc == 0
    # The boot prefix runs in this exact order, then the supervisor.
    boot_prefix = [
        "init_observability",
        "run_startup",
        "init_pool",
        "recover_stale_scans",
        "recover_stale_ingestion_runs",
        "budget",
        "open_async",
        "apply_schema",
        "supervisor",
    ]
    assert order[: len(boot_prefix)] == boot_prefix
    mocks["supervisor"].assert_called_once()


@pytest.mark.asyncio
async def test_exits_nonzero_when_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unmigrated DB → exit 1 BEFORE opening the connector or supervisor."""
    import app.worker_main as wm

    order: list[str] = []
    mocks = _patch_boot(monkeypatch, healthy=False, order=order)

    rc = await wm.main()

    assert rc == 1
    mocks["open_async"].assert_not_called()
    mocks["supervisor"].assert_not_called()
    assert "init_pool" not in order  # short-circuited right after run_startup


@pytest.mark.asyncio
async def test_teardown_is_bounded_and_ordered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Teardown cancels the worker, then closes the connector, flushes PostHog,
    closes the pool — in that order, all via the bounded helpers."""
    import app.worker_main as wm

    order: list[str] = []
    _patch_boot(monkeypatch, healthy=True, order=order)

    teardown: list[str] = []

    async def rec_cancel(task: object, timeout: float, label: str) -> None:  # noqa: ASYNC109
        teardown.append(f"cancel:{label}")

    async def rec_bounded(coro: Any, timeout: float, label: str) -> None:  # noqa: ASYNC109
        teardown.append(f"bounded:{label}")
        if asyncio.iscoroutine(coro):
            await coro  # drain it so no 'coroutine never awaited' warning

    monkeypatch.setattr(wm, "cancel_and_settle", rec_cancel)
    monkeypatch.setattr(wm, "bounded", rec_bounded)

    rc = await wm.main()

    assert rc == 0
    assert teardown == [
        "cancel:ingestion worker",
        "bounded:procrastinate close",
        "bounded:posthog flush",
        "bounded:db pool close",
    ]
