"""Run one adapter cycle by hand (ops + offline testing).

`python -m app.ingestion.run_one_cycle <source>` — e.g. mcp_registry / github_topics /
npm / pypi. Runs the registered adapter's run_cycle once against the live source
(subject to the same allowlist + rate limit + Hishel cache as the worker).
"""

from __future__ import annotations

import asyncio
import sys

import structlog

from app.ingestion.tasks import run_source_cycle

logger = structlog.get_logger(__name__)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m app.ingestion.run_one_cycle <source>", file=sys.stderr)
        return 2
    source = sys.argv[1]
    counters = asyncio.run(run_source_cycle(source, trigger="manual"))
    print(counters)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
