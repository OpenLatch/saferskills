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
from saferskills_admin.domains.sources.tui.client import HealthClientError

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


def _notifs(app: SourcesDashboardApp) -> list[Any]:
    return list(app._notifications._notifications.values())  # noqa: SLF001


def test_force_cycle_success_notifies() -> None:
    # A successful action must give visible feedback (a toast) — previously a
    # success was silent, reading as "nothing happened".
    async def scenario() -> None:
        client = FakeClient()
        app = SourcesDashboardApp(client)
        async with app.run_test(notifications=True) as pilot:
            await _settle(pilot)
            app.push_screen(SourceDetailScreen(client, "npm"))
            await _settle(pilot)
            await pilot.press("c")
            await _settle(pilot)
            await pilot.click("#confirm-yes")
            await _settle(pilot, ticks=10)
            notes = _notifs(app)
            assert any(n.severity == "information" and "force-cycle" in n.message for n in notes)

    asyncio.run(scenario())


def test_force_cycle_shows_persistent_inline_status() -> None:
    # The unmissable confirmation: a persistent inline line (#action-status)
    # that updates on confirm and is NOT wiped by the 5s auto-refresh.
    async def scenario() -> None:
        client = FakeClient()
        app = SourcesDashboardApp(client)
        async with app.run_test() as pilot:
            await _settle(pilot)
            app.push_screen(SourceDetailScreen(client, "npm"))
            await _settle(pilot)
            await pilot.press("c")
            await _settle(pilot)
            await pilot.click("#confirm-yes")
            await _settle(pilot, ticks=10)
            status = app.screen.query_one("#action-status", Static)
            rendered = str(status.render())
            assert "force-cycle" in rendered and "accepted" in rendered
            # survives an extra refresh cycle (not wiped like #detail-error)
            app.screen.load()
            await _settle(pilot, ticks=10)
            assert "accepted" in str(status.render())

    asyncio.run(scenario())


def test_force_cycle_survives_concurrent_autorefresh() -> None:
    # Regression: SourceDetailScreen.load is @work(exclusive=True) and shared the
    # default worker group with _confirm_action (same screen node). A 5s
    # auto-refresh load() tick that fired while the confirm modal was open
    # CANCELLED the pending confirm worker — clicking Confirm then did nothing:
    # no force_cycle call, no inline status, no toast (the exact "no visual
    # confirmation" symptom). load() now has its own group so its exclusive
    # cancellation can't reach the action worker.
    async def scenario() -> None:
        client = FakeClient()
        app = SourcesDashboardApp(client)
        async with app.run_test(notifications=True) as pilot:
            await _settle(pilot)
            detail = SourceDetailScreen(client, "npm")
            app.push_screen(detail)
            await _settle(pilot)
            await pilot.press("c")  # opens the modal; _confirm_action awaits the gate
            await _settle(pilot)
            # Simulate the 5s auto-refresh firing while the modal is up. Under the
            # bug this exclusive load() cancels the in-flight _confirm_action.
            detail.load()
            detail.load()
            await _settle(pilot)
            await pilot.click("#confirm-yes")
            await _settle(pilot, ticks=12)
            assert client.force_cycle_calls == ["npm"]
            status = detail.query_one("#action-status", Static)
            assert "accepted" in str(status.render())

    asyncio.run(scenario())


def test_action_status_shows_failure_inline() -> None:
    class RaisingClient(FakeClient):
        def force_cycle(self, source: str) -> dict[str, Any]:
            raise HealthClientError("HTTP 400 not schedulable")

    async def scenario() -> None:
        client = RaisingClient()
        app = SourcesDashboardApp(client)
        async with app.run_test() as pilot:
            await _settle(pilot)
            app.push_screen(SourceDetailScreen(client, "github_skills"))
            await _settle(pilot)
            await pilot.press("c")
            await _settle(pilot)
            await pilot.click("#confirm-yes")
            await _settle(pilot, ticks=10)
            rendered = str(app.screen.query_one("#action-status", Static).render())
            assert "failed" in rendered and "not schedulable" in rendered

    asyncio.run(scenario())


def test_force_cycle_failure_notifies() -> None:
    # Regression: a failing action (e.g. force-cycle on a webhook source → HTTP
    # 400) must surface a persistent error toast. Writing to #detail-error alone
    # was wiped within 5s by the auto-refresh load(), so the user saw nothing.
    class RaisingClient(FakeClient):
        def force_cycle(self, source: str) -> dict[str, Any]:
            raise HealthClientError(f"HTTP 400 source {source!r} is not schedulable")

    async def scenario() -> None:
        client = RaisingClient()
        app = SourcesDashboardApp(client)
        async with app.run_test(notifications=True) as pilot:
            await _settle(pilot)
            app.push_screen(SourceDetailScreen(client, "github_skills"))
            await _settle(pilot)
            await pilot.press("c")
            await _settle(pilot)
            await pilot.click("#confirm-yes")
            await _settle(pilot, ticks=10)
            notes = _notifs(app)
            assert any(n.severity == "error" and "not schedulable" in n.message for n in notes)

    asyncio.run(scenario())


def test_dashboard_shows_loading_until_first_snapshot() -> None:
    # Regression: the sources table must show a loading spinner while the first
    # fetch is in flight, then clear it — otherwise the dashboard renders a bare
    # empty grid with no indication anything is happening.
    import threading

    class GatedClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.gate = threading.Event()

        def snapshot(self) -> dict[str, Any]:
            self.gate.wait(timeout=5)
            return _snapshot()

    async def scenario() -> None:
        client = GatedClient()
        app = SourcesDashboardApp(client)
        async with app.run_test() as pilot:
            await _settle(pilot)  # load() worker started, blocked on the gate
            table = app.query_one("#sources-table", DataTable)
            assert table.loading is True
            client.gate.set()  # release the snapshot fetch
            await _settle(pilot, ticks=12)
            assert table.loading is False
            assert table.row_count == 2

    asyncio.run(scenario())


def test_q_quits_the_app() -> None:
    # Regression: `q` was a no-op — a screen-defined `quit` binding does not
    # resolve up to App.action_quit, so the screen needs its own action_quit.
    async def scenario() -> None:
        app = SourcesDashboardApp(FakeClient())
        async with app.run_test() as pilot:
            await _settle(pilot)
            await pilot.press("q")
            await _settle(pilot)
            assert app.is_running is False

    asyncio.run(scenario())


def test_r_refresh_blinks_and_reloads() -> None:
    # `r` must give visible feedback (a brief blink) AND re-fetch.
    class CountingClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.snapshot_calls = 0

        def snapshot(self) -> dict[str, Any]:
            self.snapshot_calls += 1
            return _snapshot()

    async def scenario() -> None:
        client = CountingClient()
        app = SourcesDashboardApp(client)
        async with app.run_test() as pilot:
            await _settle(pilot)
            before = client.snapshot_calls
            table = app.query_one("#sources-table", DataTable)
            app.screen.action_refresh()  # synchronously adds the blink class
            assert table.has_class("refreshing") is True
            await _settle(pilot, ticks=10)  # blink timer fires + reload completes
            assert table.has_class("refreshing") is False
            assert client.snapshot_calls > before

    asyncio.run(scenario())


def test_detail_errors_panel_shows_full_message() -> None:
    # The run-history table only shows error_class; the Errors panel must surface
    # the full error_message so failures are diagnosable from the dashboard.
    class ErroringClient(FakeClient):
        def runs(
            self, source: str, *, before: str | None = None, limit: int = 50
        ) -> dict[str, Any]:
            return {
                "data": [
                    {
                        "id": "e1",
                        "source": source,
                        "trigger": "scheduled",
                        "status": "failed",
                        "started_at": "2026-06-04T11:50:00+00:00",
                        "duration_ms": 1200,
                        "items_seen": 0,
                        "items_added": 0,
                        "items_updated": 0,
                        "attempt": 1,
                        "error_class": "IngestionRetry",
                        "error_message": "rate limit exceeded fetching api.github.com",
                    }
                ],
                "next_before": None,
            }

    async def scenario() -> None:
        client = ErroringClient()
        app = SourcesDashboardApp(client)
        async with app.run_test() as pilot:
            await _settle(pilot)
            app.push_screen(SourceDetailScreen(client, "npm"))
            await _settle(pilot, ticks=10)
            panel = app.screen.query_one("#errors-list", Static)
            rendered = str(panel.render())
            assert "IngestionRetry" in rendered
            assert "rate limit exceeded fetching api.github.com" in rendered
            # heading turns red only because there are errors
            assert app.screen.query_one("#errors-title").has_class("has-errors")

    asyncio.run(scenario())


def test_detail_errors_panel_empty_when_no_errors() -> None:
    async def scenario() -> None:
        client = FakeClient()  # npm run succeeded, no errors
        app = SourcesDashboardApp(client)
        async with app.run_test() as pilot:
            await _settle(pilot)
            app.push_screen(SourceDetailScreen(client, "npm"))
            await _settle(pilot, ticks=10)
            panel = app.screen.query_one("#errors-list", Static)
            assert "no errors" in str(panel.render())
            # heading is NOT red when there are no errors
            assert not app.screen.query_one("#errors-title").has_class("has-errors")

    asyncio.run(scenario())


def test_confirm_modal_arrow_navigation_and_keys() -> None:
    # Regression: the confirm dialog must be keyboard-navigable — arrows move
    # focus between the two buttons, and y/n resolve it without the mouse.
    from saferskills_admin.domains.sources.tui.app import ConfirmModal

    async def scenario() -> None:
        app = SourcesDashboardApp(FakeClient())
        async with app.run_test() as pilot:
            await _settle(pilot)
            app.push_screen(SourceDetailScreen(FakeClient(), "npm"))
            await _settle(pilot)

            # arrows move focus left/right between Confirm and Cancel
            await pilot.press("c")
            await _settle(pilot)
            assert isinstance(app.screen, ConfirmModal)
            await pilot.press("right")
            await _settle(pilot)
            assert app.focused.id == "confirm-no"
            await pilot.press("left")
            await _settle(pilot)
            assert app.focused.id == "confirm-yes"

            # n cancels (dismisses the modal without acting)
            await pilot.press("n")
            await _settle(pilot)
            assert isinstance(app.screen, SourceDetailScreen)

    asyncio.run(scenario())


def test_confirm_modal_y_confirms() -> None:
    async def scenario() -> None:
        client = FakeClient()
        app = SourcesDashboardApp(client)
        async with app.run_test() as pilot:
            await _settle(pilot)
            app.push_screen(SourceDetailScreen(client, "npm"))
            await _settle(pilot)
            await pilot.press("c")
            await _settle(pilot)
            await pilot.press("y")  # y confirms
            await _settle(pilot, ticks=10)
            assert client.force_cycle_calls == ["npm"]

    asyncio.run(scenario())


def test_force_cycle_all_confirms_and_cycles_every_source() -> None:
    # `c` on the landing screen force-cycles EVERY source in the snapshot after a
    # confirm, and reports an all-acknowledged inline status + toast.
    async def scenario() -> None:
        client = FakeClient()
        app = SourcesDashboardApp(client)
        async with app.run_test(notifications=True) as pilot:
            await _settle(pilot)
            await pilot.press("c")  # force-cycle-all → ConfirmModal
            await _settle(pilot)
            await pilot.click("#confirm-yes")
            await _settle(pilot, ticks=12)
            assert sorted(client.force_cycle_calls) == ["npm", "smithery"]
            status = app.screen.query_one("#action-status", Static)
            rendered = str(status.render())
            assert "force-cycle ALL" in rendered and "acknowledged" in rendered
            notes = _notifs(app)
            assert any(n.severity == "information" and "acknowledged" in n.message for n in notes)

    asyncio.run(scenario())


def test_force_cycle_all_reports_partial_failure() -> None:
    # When one source fails the gate (a webhook source the backend won't schedule →
    # a reworded 400), the others still go through and the status reports the tally.
    class PartialClient(FakeClient):
        def force_cycle(self, source: str) -> dict[str, Any]:
            if source == "smithery":
                raise HealthClientError(
                    "HTTP 400 'smithery' has no periodic cycle (webhook or disabled source)",
                    status_code=400,
                )
            return super().force_cycle(source)

    async def scenario() -> None:
        client = PartialClient()
        app = SourcesDashboardApp(client)
        async with app.run_test(notifications=True) as pilot:
            await _settle(pilot)
            await pilot.press("c")
            await _settle(pilot)
            await pilot.click("#confirm-yes")
            await _settle(pilot, ticks=12)
            assert client.force_cycle_calls == ["npm"]  # smithery raised
            rendered = str(app.screen.query_one("#action-status", Static).render())
            assert "1/2 acknowledged" in rendered and "1 failed" in rendered
            assert "no periodic cycle" in rendered  # the accurate webhook reason
            notes = _notifs(app)
            assert any(n.severity == "warning" and "failed" in n.message for n in notes)

    asyncio.run(scenario())


def test_force_cycle_all_tallies_409_as_acknowledged() -> None:
    # A source already mid-cycle returns 409 — it IS schedulable, just busy — so it
    # must be tallied as acknowledged-with-note, NEVER as a hard failure (the old
    # broad-except backend message mislabelled this "not schedulable / N failed").
    class BusyClient(FakeClient):
        def force_cycle(self, source: str) -> dict[str, Any]:
            if source == "smithery":
                raise HealthClientError(
                    "HTTP 409 a cycle is already queued or running for 'smithery'",
                    status_code=409,
                )
            return super().force_cycle(source)

    async def scenario() -> None:
        client = BusyClient()
        app = SourcesDashboardApp(client)
        async with app.run_test(notifications=True) as pilot:
            await _settle(pilot)
            await pilot.press("c")
            await _settle(pilot)
            await pilot.click("#confirm-yes")
            await _settle(pilot, ticks=12)
            assert client.force_cycle_calls == ["npm"]  # smithery raised 409
            rendered = str(app.screen.query_one("#action-status", Static).render())
            # No hard failure — all acknowledged, with the busy source noted.
            assert "force-cycle ALL 2 sources acknowledged" in rendered
            assert "1 already running" in rendered
            assert "failed" not in rendered
            notes = _notifs(app)
            assert any(n.severity == "information" and "acknowledged" in n.message for n in notes)

    asyncio.run(scenario())


def test_force_cycle_all_cancel_does_nothing() -> None:
    async def scenario() -> None:
        client = FakeClient()
        app = SourcesDashboardApp(client)
        async with app.run_test() as pilot:
            await _settle(pilot)
            await pilot.press("c")
            await _settle(pilot)
            await pilot.press("n")  # cancel the confirm
            await _settle(pilot, ticks=8)
            assert client.force_cycle_calls == []

    asyncio.run(scenario())


def test_dashboard_help_smoke() -> None:
    result = runner.invoke(cli_app, ["sources", "dashboard", "--help"])
    assert result.exit_code == 0
    assert "dashboard" in result.output.lower()


def test_runs_help_smoke() -> None:
    result = runner.invoke(cli_app, ["sources", "runs", "--help"])
    assert result.exit_code == 0
    assert "history" in result.output.lower()
