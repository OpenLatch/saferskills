"""argparse-driven dispatcher for the SaferSkills E2E suite.

One subcommand per registered command. Each subcommand inherits the
global flags (`--api-url`, `--base-url`) via an `argparse.ArgumentParser`
parent. `main` resolves the `Config`, dispatches to the chosen
command's `async run(config)`, and maps top-level exceptions to the
right `ExitCode`.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from pydantic import ValidationError

from saferskills_e2e.commands import ALL_COMMANDS
from saferskills_e2e.commands.base import BaseCommand
from saferskills_e2e.shared.config import Config
from saferskills_e2e.shared.exit_codes import ExitCode
from saferskills_e2e.shared.output import print_fail


def _add_global_args(parser: argparse.ArgumentParser) -> None:
    """Register the URL overrides on a parser.

    Used twice: once on the root parser (so `saferskills-e2e --api-url
    ... doctor` works) and once on each subcommand parser (so
    `saferskills-e2e doctor --api-url ...` also works). The CLI dance
    is mirrored from openlatch-platform/tools/e2e — argparse won't
    merge a flag declared only on the root into subparser namespaces.
    """
    parser.add_argument(
        "--api-url",
        default=None,
        help="SaferSkills API root URL (env: SAFERSKILLS_API_URL, default: http://localhost:8000)",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Public marketing site root URL (env: SAFERSKILLS_BASE_URL, "
        "default: http://localhost:5173)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=None,
        help="Transient-failure retry attempts for data-plane HTTP calls "
        "(default: 3). Retries only 502/503/504 + connect/read timeouts.",
    )
    parser.add_argument(
        "--retry-backoff",
        type=float,
        default=None,
        dest="retry_backoff",
        help="Base exponential backoff (seconds) between retries (default: 1.0).",
    )


def _build_parser() -> tuple[argparse.ArgumentParser, dict[str, BaseCommand]]:
    """Return the configured root parser plus a `name -> instance`
    map of already-constructed command instances.

    Constructing the commands here means `cli.main` doesn't have to
    instantiate them again — a small simplification that also lets
    `--help` show each command's `description` field verbatim.
    """
    parent = argparse.ArgumentParser(add_help=False)
    _add_global_args(parent)

    parser = argparse.ArgumentParser(
        prog="saferskills-e2e",
        description="End-to-end test orchestrator for the SaferSkills platform.",
        parents=[parent],
    )

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    instances: dict[str, BaseCommand] = {}
    for name, cmd_cls in ALL_COMMANDS.items():
        cmd = cmd_cls()
        instances[name] = cmd
        subparsers.add_parser(
            name,
            help=cmd.description,
            description=cmd.description,
            parents=[parent],
        )

    return parser, instances


def main() -> int:
    """Entry point used by both the console script and `python -m`."""
    parser, instances = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return int(ExitCode.FAIL_CONFIG)

    try:
        config = Config.from_args(args)
    except ValidationError as e:
        print_fail(f"Invalid configuration: {e!s}")
        return int(ExitCode.FAIL_CONFIG)

    cmd = instances[args.command]

    try:
        code = asyncio.run(cmd.run(config))
    except KeyboardInterrupt:
        # 130 = SIGINT — standard shell convention for "user cancelled".
        return 130
    except Exception as e:
        print_fail(f"Unhandled error in {cmd.name}: {e!r}")
        return int(ExitCode.FAIL_UNKNOWN)

    return int(code)


if __name__ == "__main__":
    sys.exit(main())
