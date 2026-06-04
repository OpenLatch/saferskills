"""Textual pilot tests for the eagle-eye dashboard + CLI smoke (no network)."""

from __future__ import annotations

import asyncio
from typing import Any

from textual.widgets import DataTable, Static
from typer.testing import CliRunner

from saferskills_admin.cli import app as cli_app
from saferskills_admin.domains.sources.tui.app import (
    DashboardScreen,
    SourceDetailScreen,
    SourcesDashboardApp,
)

runner = CliRunner()


def _snapshot() -> dict[str, Any]:
    return {
        "generated_at": "2026-06-04T12:00:00+00:00",
        "summary": {
            "overall": "critical",
            "total": 2,
            "by_status": {"healthy": 1, "blocked": 1},
            "critical_count": 1,
            "warn_count": 0,
        },
        "critical": [
            {
                "source": "smithery",
                "reason_code": "blocked",
                "tier": "critical",
                "detail": "blocked",
            }
        ],
        "data": [
            {
                "source": "npm",
                "kind": "api",
                "cadence": "0 * * * *",
                "enabled": True,
                "status": "active",
                "consecutive_failure_count": 0,
                "live": {"running": False, "running_since": None, "dead_letter": False},
                "last_run": {
                    "id": "r1",
                    "trigger": "scheduled",
                    "status": "succeeded",
                    "started_at": "2026-06-04T11:55:00+00:00",
                    "ended_at": "2026-06-04T11:55:02+00:00",
                    "duration_ms": 2000,
                    "items_seen": 9,
                    "items_added": 3,
                    "items_updated": 1,
                    "http_304_count": 4,
                    "http_5xx_count": 0,
                    "error_class": None,
                    "error_message": None,
                },
                "schedule": {
                    "cadence_cron": "0 * * * *",
                    "next_expected_run": "2026-06-04T13:00:00+00:00",
                    "next_retry_at": None,
                    "overdue": False,
                },
                "health": {
                    "status": "healthy",
                    "reason_code": None,
                    "tier": None,
                    "failure_rate_1h": 0.0,
                    "failure_rate_24h": 0.0,
                    "runs_24h": 5,
                    "consecutive_failures": 0,
                    "last_success_at": "2026-06-04T11:55:00+00:00",
                    "last_attempt_at": "2026-06-04T11:55:00+00:00",
                },
            },
            {
                "source": "smithery",
                "kind": "scrape",
                "cadence": "0 */6 * * *",
                "enabled": True,
                "status": "blocked",
                "consecutive_failure_count": 9,
                "live": {"running": False, "running_since": None, "dead_letter": False},
                "last_run": None,
                "schedule": {
                    "cadence_cron": "0 */6 * * *",
                    "next_expected_run": "2026-06-04T18:00:00+00:00",
                    "next_retry_at": None,
                    "overdue": False,
                },
                "health": {
                    "status": "blocked",
                    "reason_code": "blocked",
                    "tier": "critical",
                    "failure_rate_1h": 0.0,
                    "failure_rate_24h": 0.0,
                    "runs_24h": 0,
                    "consecutive_failures": 9,
                    "last_success_at": None,
                    "last_attempt_at": None,
                },
            },
        ],
    }


class FakeClient:
    def __init__(self) -> None:
        self.force_cycle_calls: list[str] = []
        self.pause_calls: list[str] = []

    def snapshot(self) -> dict[str, Any]:
        return _snapshot()

    def runs(self, source: str, *, before: str | None = None, limit: int = 50) -> dict[str, Any]:
        if source == "npm":
            return {
                "data": [
                    {
                        "id": "r1",
                        "source": "npm",
                        "trigger": "scheduled",
                        "status": "succeeded",
                        "started_at": "2026-06-04T11:55:00+00:00",
                        "ended_at": "2026-06-04T11:55:02+00:00",
                        "duration_ms": 2000,
                        "items_seen": 9,
                        "items_added": 3,
                        "items_updated": 1,
                        "http_304_count": 4,
                        "http_5xx_count": 0,
                        "attempt": 1,
                        "error_class": None,
                        "error_message": None,
                    }
                ],
                "next_before": None,
            }
        return {"data": [], "next_before": None}

    def force_cycle(self, source: str) -> dict[str, Any]:
        self.force_cycle_calls.append(source)
        return {"ok": True}

    def pause(self, source: str) -> dict[str, Any]:
        self.pause_calls.append(source)
        return {"ok": True}

    def unpause(self, source: str) -> dict[str, Any]:
        return {"ok": True}


async def _settle(pilot: Any, ticks: int = 6) -> None:
    for _ in range(ticks):
        await pilot.pause()


def test_dashboard_renders() -> None:
    async def scenario() -> None:
        app = SourcesDashboardApp(FakeClient())
        async with app.run_test() as pilot:
            await _settle(pilot)
            assert isinstance(app.screen, DashboardScreen)
            summary = app.query_one("#summary", Static)
            assert "Overall" in str(summary.render())
            table = app.query_one("#sources-table", DataTable)
            assert table.row_count == 2

    asyncio.run(scenario())


def test_filter_cycles_to_critical() -> None:
    async def scenario() -> None:
        app = SourcesDashboardApp(FakeClient())
        async with app.run_test() as pilot:
            await _settle(pilot)
            await pilot.press("f")  # all → critical
            await _settle(pilot)
            table = app.query_one("#sources-table", DataTable)
            assert table.row_count == 1  # only the blocked source

    asyncio.run(scenario())


def test_navigation_push_and_pop() -> None:
    async def scenario() -> None:
        app = SourcesDashboardApp(FakeClient())
        async with app.run_test() as pilot:
            await _settle(pilot)
            table = app.query_one("#sources-table", DataTable)
            app.set_focus(table)
            table.move_cursor(row=0)
            await pilot.press("enter")
            await _settle(pilot)
            assert isinstance(app.screen, SourceDetailScreen)
            await pilot.press("escape")
            await _settle(pilot)
            assert isinstance(app.screen, DashboardScreen)

    asyncio.run(scenario())


def test_detail_renders_cards_and_runs() -> None:
    async def scenario() -> None:
        client = FakeClient()
        app = SourcesDashboardApp(client)
        async with app.run_test() as pilot:
            await _settle(pilot)
            table = app.query_one("#sources-table", DataTable)
            app.set_focus(table)
            table.move_cursor(row=0)  # row 0 = npm
            await pilot.press("enter")
            await _settle(pilot)
            assert isinstance(app.screen, SourceDetailScreen)
            detail = app.screen
            await _settle(pilot)  # let the detail load() worker populate
            cards = detail.query_one("#detail-cards", Static)
            assert "npm" in str(cards.render())
            runs = detail.query_one("#runs-table", DataTable)
            assert runs.row_count == 1

    asyncio.run(scenario())


def test_force_cycle_confirm_calls_client() -> None:
    async def scenario() -> None:
        client = FakeClient()
        app = SourcesDashboardApp(client)
        async with app.run_test() as pilot:
            await _settle(pilot)
            app.push_screen(SourceDetailScreen(client, "npm"))
            await _settle(pilot)
            await pilot.press("c")  # force-cycle → ConfirmModal
            await _settle(pilot)
            await pilot.click("#confirm-yes")
            await _settle(pilot, ticks=10)
            assert client.force_cycle_calls == ["npm"]

    asyncio.run(scenario())


def test_dashboard_help_smoke() -> None:
    result = runner.invoke(cli_app, ["sources", "dashboard", "--help"])
    assert result.exit_code == 0
    assert "dashboard" in result.output.lower()


def test_runs_help_smoke() -> None:
    result = runner.invoke(cli_app, ["sources", "runs", "--help"])
    assert result.exit_code == 0
    assert "history" in result.output.lower()
