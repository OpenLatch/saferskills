"""Abstract base class for every E2E command.

Two reasons to keep this its own module:
  1. Importing `BaseCommand` from a sibling command would create a
     cycle as soon as `commands/__init__.py` imports the concrete
     subclasses.
  2. Adding a new contract field (e.g. `requires_browser`) lives in
     exactly one place.
"""

from __future__ import annotations

import abc

from saferskills_e2e.shared.config import Config
from saferskills_e2e.shared.exit_codes import ExitCode
from saferskills_e2e.shared.output import print_header


class BaseCommand(abc.ABC):
    """Every concrete command extends this ABC."""

    name: str
    """Short, lowercase identifier used on the CLI (e.g. `doctor`)."""

    description: str
    """One-line summary shown in `--help`."""

    @abc.abstractmethod
    async def run(self, config: Config) -> ExitCode:
        """Execute the command and return an `ExitCode`.

        Must be async — every I/O path in this suite is async, and
        having `run` itself be async means concrete commands don't
        need an extra `asyncio.run` wrapper.
        """

    def print_header(self) -> None:
        """Print the command's section header.

        Concrete commands call this once at the top of `run`. Kept on
        the ABC so the header format stays uniform without each
        command importing `print_header` from `shared.output`.
        """
        print_header(self.description)
