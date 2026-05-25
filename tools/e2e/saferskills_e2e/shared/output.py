"""Rich-backed print helpers — the single chokepoint for command output.

Commands MUST go through these helpers; a bare `print()` in a command
file is a review-time regression. Centralising here means a future
`--json` mode can be added by flipping one module-level switch without
touching every command.
"""

from __future__ import annotations

from collections.abc import Sequence

from rich.console import Console
from rich.table import Table

_console = Console()
_stderr_console = Console(stderr=True)


def print_header(title: str) -> None:
    """Section header. Rendered above each command's body."""
    _console.print()
    _console.rule(f"[bold]{title}[/bold]")


def print_ok(msg: str) -> None:
    """Success line — green PASS prefix."""
    _console.print(f"  [green]PASS[/green]  {msg}")


def print_warn(msg: str) -> None:
    """Warning line — yellow WARN prefix. Does not count as failure."""
    _console.print(f"  [yellow]WARN[/yellow]  {msg}")


def print_fail(msg: str) -> None:
    """Failure line — red FAIL prefix. Written to stderr so CI panes
    surface it even when stdout is captured."""
    _stderr_console.print(f"  [red]FAIL[/red]  {msg}")


def print_info(msg: str) -> None:
    """Plain informational line, no status prefix."""
    _console.print(f"  {msg}")


def print_table(rows: Sequence[Sequence[str]], headers: Sequence[str]) -> None:
    """Render a small results table.

    `rows` and `headers` are stringified by the caller — we don't try
    to format numbers here so command authors stay in control of
    precision / units.
    """
    table = Table(show_header=True, header_style="bold")
    for header in headers:
        table.add_column(header)
    for row in rows:
        table.add_row(*row)
    _console.print(table)
