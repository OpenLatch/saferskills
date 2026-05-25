"""Sequential orchestrator.

Runs every command in `COMMAND_SEQUENCE` (defined in
`saferskills_e2e.commands.__init__`) in order. Stops on the first
non-OK exit code and propagates that code so CI can branch on the
specific failure mode. Prints a Rich table summary at the end.

`AllCommand` deliberately re-imports from the package `__init__` rather
than from each sibling module — that's the single registry of "what
runs", and keeping the import edge in one direction (`all -> __init__`)
avoids a cycle.
"""

from __future__ import annotations

from saferskills_e2e.commands.base import BaseCommand
from saferskills_e2e.shared.config import Config
from saferskills_e2e.shared.exit_codes import ExitCode
from saferskills_e2e.shared.output import (
    print_fail,
    print_info,
    print_ok,
    print_table,
)
from saferskills_e2e.shared.timing import Stopwatch


class AllCommand(BaseCommand):
    name = "all"
    description = "Run doctor -> smoke -> homepage (stops on first failure)"

    async def run(self, config: Config) -> ExitCode:
        self.print_header()

        # Lazy import to break the `commands/__init__.py -> all.py
        # -> commands/__init__.py` cycle.
        from saferskills_e2e.commands import ALL_COMMANDS, COMMAND_SEQUENCE

        results: list[tuple[str, ExitCode, float]] = []
        final: ExitCode = ExitCode.OK

        for name in COMMAND_SEQUENCE:
            cmd_cls = ALL_COMMANDS[name]
            cmd = cmd_cls()
            print_info("")
            print_info(f"--- {cmd.name} ---")
            with Stopwatch() as sw:
                code = await cmd.run(config)
            results.append((cmd.name, code, sw.elapsed_ms))

            if code is not ExitCode.OK:
                print_fail(f"{cmd.name} failed with exit code {int(code)} — stopping")
                final = code
                break
            print_ok(f"{cmd.name} passed ({sw.elapsed_ms:.1f} ms)")

        # Always render the summary table — even on early exit it shows
        # which step regressed and how far the run got.
        rows = [
            (name, "PASS" if code is ExitCode.OK else f"FAIL ({int(code)})",
             f"{elapsed_ms:.1f}")
            for name, code, elapsed_ms in results
        ]
        print_info("")
        print_table(rows, headers=("Command", "Status", "Duration (ms)"))

        return final
