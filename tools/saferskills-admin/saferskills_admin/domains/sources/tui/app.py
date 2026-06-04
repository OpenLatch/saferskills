"""The eagle-eye ingestion dashboard — a Textual TUI.

Screen stack IS the navigation: `DashboardScreen` (14-source overview, 5s
auto-refresh, filter) → push `SourceDetailScreen` (live + last-run + schedule +
health + run-history) → `Esc`/`backspace` pops back. Actions (force-cycle / pause
/ unpause) go through a `ConfirmModal` then the existing admin endpoint.

Blocking HTTP is offloaded with `asyncio.to_thread` inside Textual `@work` workers
so the UI never freezes; a connection error shows a red bar and keeps the last
good snapshot. The client is injected so `run_test()` pilots can mock it.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from rich.markup import escape
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Header, Label, Static

from .client import HealthClientError, SourcesHealthClient
from .format import duration, overall_style, rel_time, run_status_style, status_style

_BLINK_SECONDS = 0.18


def _blink(widget: DataTable) -> None:
    """Briefly tint a widget (see CSS `.refreshing`) as manual-refresh feedback."""
    widget.add_class("refreshing")
    widget.set_timer(_BLINK_SECONDS, lambda: widget.remove_class("refreshing"))


class ConfirmModal(ModalScreen[bool]):
    """Yes/no gate before a mutating admin action.

    Fully keyboard-navigable: ←/→ (and h/l) move between the two buttons, Enter
    activates the focused one, y confirms, n/Esc cancels. (Tab also works, but a
    horizontal two-button row invites the arrow keys — without these bindings the
    arrows were dead and the dialog felt un-navigable.)
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("left,up,h", "focus_confirm", show=False),
        Binding("right,down,l", "focus_cancel", show=False),
        Binding("y", "confirm", show=False),
        Binding("n", "cancel", show=False),
    ]

    def __init__(self, prompt: str) -> None:
        super().__init__()
        self._prompt = prompt

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Label(self._prompt, id="confirm-prompt")
            with Horizontal(id="confirm-buttons"):
                yield Button("Confirm", variant="error", id="confirm-yes")
                yield Button("Cancel", variant="primary", id="confirm-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-yes")

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_focus_confirm(self) -> None:
        self.query_one("#confirm-yes", Button).focus()

    def action_focus_cancel(self) -> None:
        self.query_one("#confirm-no", Button).focus()


class SourceDetailScreen(Screen[None]):
    """Drill-down for one source: cards + run history. Esc/backspace goes back."""

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("backspace", "back", "Back"),
        Binding("c", "force_cycle", "Force-cycle"),
        Binding("p", "pause", "Pause"),
        Binding("u", "unpause", "Unpause"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, client: SourcesHealthClient, source: str) -> None:
        super().__init__()
        self.client = client
        self.source = source

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Static("", id="detail-cards")
            yield Static("", id="action-status")
            yield Label("Run history", id="runs-title")
            yield DataTable(id="runs-table")
            yield Label("Errors", id="errors-title")
            yield Static("", id="errors-list")
        yield Static("", id="detail-error")
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"source · {self.source}"
        table = self.query_one("#runs-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Started", "Trigger", "Status", "Dur", "Seen", "Add", "Upd", "Error")
        table.loading = True  # spinner until the first fetch lands
        self.load()
        self.set_interval(5.0, self.load)

    @work(exclusive=True)
    async def load(self) -> None:
        try:
            # The snapshot + runs reads are independent — fetch them concurrently.
            snap, runs = await asyncio.gather(
                asyncio.to_thread(self.client.snapshot),
                asyncio.to_thread(self.client.runs, self.source),
            )
        except HealthClientError as exc:
            self.query_one("#detail-error", Static).update(f"[red]{exc}[/]")
            self.query_one("#runs-table", DataTable).loading = False
            return
        self.query_one("#detail-error", Static).update("")
        provider = next((p for p in snap.get("data", []) if p.get("source") == self.source), None)
        if provider is not None:
            self._render_cards(provider)
        self._render_runs(runs.get("data", []))
        self._render_errors(runs.get("data", []))
        self.query_one("#runs-table", DataTable).loading = False

    def _render_cards(self, p: dict[str, Any]) -> None:
        live = p.get("live", {})
        lr = p.get("last_run") or {}
        sched = p.get("schedule", {})
        h = p.get("health", {})
        status = h.get("status", "?")
        running = (
            f"running since {rel_time(live.get('running_since'))}"
            if live.get("running")
            else "idle"
        )
        last = (
            f"{lr.get('status', '?')} · {rel_time(lr.get('started_at'))} · "
            f"{duration(lr.get('duration_ms'))} · "
            f"+{lr.get('items_added', '-')}/~{lr.get('items_updated', '-')} "
            f"(seen {lr.get('items_seen', '-')})"
            if lr
            else "no runs yet"
        )
        err = lr.get("error_message")
        overdue = " [yellow](overdue)[/]" if sched.get("overdue") else ""
        retry = sched.get("next_retry_at")
        lines = [
            f"[b]{p.get('source')}[/]  [{status_style(status)}]{status}[/]"
            f"   kind={p.get('kind')}  cadence={p.get('cadence') or '—'}",
            f"[b]Live[/]      {running}"
            + ("  [red](dead-letter)[/]" if live.get("dead_letter") else ""),
            f"[b]Last run[/]  {last}",
            (f"[red]          {err}[/]" if err else ""),
            f"[b]Schedule[/]  next {rel_time(sched.get('next_expected_run'))}{overdue}"
            + (f"  retry {rel_time(retry)}" if retry else ""),
            f"[b]Health[/]    fail {h.get('failure_rate_1h', 0):.0%}/1h "
            f"{h.get('failure_rate_24h', 0):.0%}/24h  "
            f"streak={h.get('consecutive_failures', 0)}  "
            f"last-success {rel_time(h.get('last_success_at'))}  runs24h={h.get('runs_24h', 0)}",
        ]
        self.query_one("#detail-cards", Static).update("\n".join(filter(None, lines)))

    def _render_runs(self, runs: list[dict[str, Any]]) -> None:
        table = self.query_one("#runs-table", DataTable)
        table.clear()
        for r in runs:
            st = r.get("status", "?")
            colour = run_status_style(st)
            table.add_row(
                rel_time(r.get("started_at")),
                r.get("trigger", "—"),
                Text(st, style=colour),
                duration(r.get("duration_ms")),
                str(r.get("items_seen", "—")),
                str(r.get("items_added", "—")),
                str(r.get("items_updated", "—")),
                (r.get("error_class") or ""),
            )

    def _render_errors(self, runs: list[dict[str, Any]]) -> None:
        """List every recent run carrying an error, with the full message.

        The run-history table only has room for `error_class`; this panel shows
        the full `error_message` (bounded ≤2048 chars server-side) so failures
        are diagnosable without leaving the dashboard. Built as a rich `Text`
        (not markup) so an error body containing `[...]` can't break rendering.
        """
        errored = [r for r in runs if r.get("error_message") or r.get("error_class")]
        # Red heading only when something actually failed.
        self.query_one("#errors-title", Label).set_class(bool(errored), "has-errors")
        panel = self.query_one("#errors-list", Static)
        if not errored:
            panel.update("[dim]no errors in recent runs[/]")
            return
        body = Text()
        for r in errored:
            cls = r.get("error_class") or "error"
            body.append(f"{rel_time(r.get('started_at'))}  ", style="dim")
            body.append(f"{cls}\n", style="bold red")
            msg = r.get("error_message")
            if msg:
                body.append(f"{msg}\n", style="red")
            body.append("\n")
        panel.update(body)

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_refresh(self) -> None:
        _blink(self.query_one("#runs-table", DataTable))
        self.load()

    def action_force_cycle(self) -> None:
        self._confirm_action("force-cycle", self.client.force_cycle)

    def action_pause(self) -> None:
        self._confirm_action("pause", self.client.pause)

    def action_unpause(self) -> None:
        self._confirm_action("unpause", self.client.unpause)

    @work
    async def _confirm_action(self, verb: str, fn: Any) -> None:
        ok = await self.app.push_screen_wait(ConfirmModal(f"{verb} '{self.source}'?"))
        if not ok:
            return
        # A PERSISTENT inline line (not a toast) — toasts auto-dismiss in ~5s
        # and overlay in a corner, easy to miss. This updates the instant you
        # confirm (before the round-trip), so there is always visible feedback
        # even if the API is slow/down. load() never clears it (unlike
        # #detail-error), so it stays until the next action.
        status = self.query_one("#action-status", Static)
        status.update(f"[yellow]⟳ {escape(verb)} '{escape(self.source)}' — sending…[/]")
        try:
            await asyncio.to_thread(fn, self.source)
        except HealthClientError as exc:
            status.update(f"[red]✗ {escape(verb)} failed — {escape(str(exc))}[/]")
            self.notify(str(exc), title=f"{verb} failed", severity="error", markup=False)
            return
        now = time.strftime("%H:%M:%S")
        status.update(
            f"[green]✓ {escape(verb)} '{escape(self.source)}' accepted at {now}[/]"
            "  [dim]— watch Live / Run history below[/]"
        )
        self.notify(f"✓ {verb} '{self.source}' accepted", severity="information", timeout=8)
        # Re-poll a few times so the result surfaces promptly: a force-cycle's
        # new run row + the brief `running` state, or a pause/unpause status
        # flip — instead of waiting up to 5s for the next auto-refresh (a fast
        # cycle can otherwise start AND finish entirely between two polls, so
        # the status looks like it never moved). _blink draws the eye to it.
        _blink(self.query_one("#runs-table", DataTable))
        self.load()
        for delay in (0.8, 1.8, 3.2, 5.0):
            self.set_timer(delay, self.load)


class DashboardScreen(Screen[None]):
    """14-source overview with a 5s auto-refresh + all/critical/running filter."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("f", "cycle_filter", "Filter"),
        # `app.quit` (namespaced) resolves to App.action_quit; a bare `quit`
        # binding on a screen does NOT bubble up, so it would be a no-op.
        Binding("q", "app.quit", "Quit"),
    ]
    _FILTERS = ("all", "critical", "running")

    def __init__(self, client: SourcesHealthClient) -> None:
        super().__init__()
        self.client = client
        self._snapshot: dict[str, Any] | None = None
        self._filter = "all"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("", id="summary")
        yield Static("", id="critical")
        yield Static("", id="error")
        yield DataTable(id="sources-table")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Ingestion Eagle-Eye"
        table = self.query_one("#sources-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Source", "Status", "Last run", "Added/Upd", "Next run", "Fails")
        table.loading = True  # spinner until the first snapshot lands
        self.query_one("#summary", Static).update("[dim]Loading sources…[/]")
        self.load()
        self.set_interval(5.0, self.load)

    @work(exclusive=True)
    async def load(self) -> None:
        try:
            snap = await asyncio.to_thread(self.client.snapshot)
        except HealthClientError as exc:
            self.query_one("#error", Static).update(
                f"[red]connection error: {exc} — showing last snapshot[/]"
            )
            self.query_one("#sources-table", DataTable).loading = False
            return
        self.query_one("#error", Static).update("")
        self._snapshot = snap
        self._apply_snapshot(snap)
        self.query_one("#sources-table", DataTable).loading = False

    def _filtered(self, data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self._filter == "critical":
            return [p for p in data if (p.get("health") or {}).get("tier")]
        if self._filter == "running":
            return [p for p in data if (p.get("health") or {}).get("status") == "running"]
        return data

    def _apply_snapshot(self, snap: dict[str, Any]) -> None:
        summary = snap.get("summary", {})
        overall = summary.get("overall", "?")
        colour = overall_style(overall)
        by = summary.get("by_status", {})
        by_txt = "  ".join(f"{k}={v}" for k, v in sorted(by.items()))
        self.query_one("#summary", Static).update(
            f"Overall [{colour} b]{overall}[/]   "
            f"total={summary.get('total', 0)}  "
            f"critical={summary.get('critical_count', 0)}  "
            f"warn={summary.get('warn_count', 0)}   {by_txt}   "
            f"[dim]filter={self._filter}[/]"
        )
        crit = snap.get("critical", [])
        if crit:
            parts = [
                f"[{'red' if c['tier'] == 'critical' else 'yellow'}]{c['source']}:"
                f"{c['reason_code']}[/]"
                for c in crit
            ]
            self.query_one("#critical", Static).update("⚠ " + "  ".join(parts))
        else:
            self.query_one("#critical", Static).update("[green]✓ all sources nominal[/]")

        table = self.query_one("#sources-table", DataTable)
        table.clear()
        for p in self._filtered(snap.get("data", [])):
            h = p.get("health") or {}
            lr = p.get("last_run") or {}
            sched = p.get("schedule") or {}
            status = h.get("status", "?")
            table.add_row(
                p.get("source", "?"),
                Text(status, style=status_style(status)),
                rel_time(lr.get("started_at")),
                f"{lr.get('items_added', '—')}/{lr.get('items_updated', '—')}",
                rel_time(sched.get("next_expected_run")),
                str(p.get("consecutive_failure_count", 0)),
                key=p.get("source"),
            )

    def action_refresh(self) -> None:
        _blink(self.query_one("#sources-table", DataTable))
        self.load()

    def action_cycle_filter(self) -> None:
        idx = self._FILTERS.index(self._filter)
        self._filter = self._FILTERS[(idx + 1) % len(self._FILTERS)]
        if self._snapshot is not None:
            self._apply_snapshot(self._snapshot)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        source = event.row_key.value
        if source:
            self.app.push_screen(SourceDetailScreen(self.client, source))


class SourcesDashboardApp(App[None]):
    """Root app — owns the screen stack + the injected health client."""

    TITLE = "SaferSkills — Ingestion"
    CSS = """
    #summary { padding: 0 1; height: auto; }
    #critical { padding: 0 1; height: auto; }
    #error { padding: 0 1; height: auto; color: red; }
    #sources-table { height: 1fr; }
    /* Brief blink overlay so a manual refresh (r) gives visible feedback. */
    DataTable.refreshing { tint: $accent 40%; }
    #detail-cards { padding: 1 1; height: auto; }
    #action-status { padding: 0 1; height: auto; text-style: bold; }
    #runs-title { padding: 1 1 0 1; text-style: bold; }
    #runs-table { height: auto; }
    #errors-title { padding: 1 1 0 1; text-style: bold; }
    #errors-title.has-errors { color: red; }
    #errors-list { padding: 0 1 1 1; height: auto; }
    #detail-error { padding: 0 1; height: auto; color: red; }
    #confirm-box {
        width: 50; height: auto; padding: 1 2;
        border: thick $accent; background: $surface;
        align: center middle;
    }
    #confirm-buttons { height: auto; align: center middle; padding-top: 1; }
    #confirm-buttons Button { margin: 0 1; }
    ConfirmModal { align: center middle; }
    """

    def __init__(self, client: SourcesHealthClient) -> None:
        super().__init__()
        self._client = client

    def get_default_screen(self) -> DashboardScreen:
        # DashboardScreen IS the base screen — drill-downs push on top of it.
        return DashboardScreen(self._client)
