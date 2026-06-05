"""Escalating retry schedule for ingestion tasks (D-04-03: 1m → 5m → 30m → 6h).

Procrastinate's built-in RetryStrategy only does constant / linear / exponential
backoff, none of which matches the plan's 1m/5m/30m/6h schedule. A tiny custom
BaseRetryStrategy gives the exact schedule, then dead-letters (max 4 attempts).

Retry taxonomy (robustness overhaul, WS-3): a PERMANENT error — provider
shape-drift surfacing as `KeyError`/`ValueError`/`TypeError`/`AttributeError`/
`IndexError`/`pydantic.ValidationError` — does NOT get better on retry; a 4x
re-attempt just burns four full-feed refetches + four tracebacks. So a permanent
class dead-letters IMMEDIATELY (`None`). The 1m/5m/30m/6h schedule is reserved
for transient / unknown failures (`httpx.HTTPError`, `OSError`, transient DB)
that a later attempt might clear. Note: most expected provider/transport failures
never reach the retry strategy at all — `run_source_cycle` catches them and
returns without re-raising; this taxonomy is the backstop for whatever DOES
re-raise out of a cycle.
"""

from __future__ import annotations

from procrastinate import BaseRetryStrategy, RetryDecision
from procrastinate.jobs import Job

_SCHEDULE_SECONDS = (60, 300, 1800, 21600)  # 1m, 5m, 30m, 6h

# Shape-drift / programming errors: deterministic, so a retry just re-fails.
_PERMANENT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    KeyError,
    ValueError,  # ValidationError subclasses ValueError; listed for explicitness below
    TypeError,
    AttributeError,
    IndexError,
)


def is_permanent_failure(exception: BaseException) -> bool:
    """True for a deterministic shape-drift / programming error (dead-letter now).

    `pydantic.ValidationError` is matched explicitly: it subclasses `ValueError`
    in Pydantic v2 (so it is already covered), but checking the import directly
    keeps the intent legible and survives any future base-class change."""
    try:
        from pydantic import ValidationError

        if isinstance(exception, ValidationError):
            return True
    except Exception:  # pragma: no cover - pydantic always importable here
        pass
    return isinstance(exception, _PERMANENT_EXCEPTIONS)


class IngestionRetry(BaseRetryStrategy):
    max_attempts = len(_SCHEDULE_SECONDS)

    def get_retry_decision(self, *, exception: BaseException, job: Job) -> RetryDecision | None:
        # Permanent errors never improve on retry — dead-letter immediately so we
        # don't burn 4x full-feed refetch + 4 tracebacks on one shape-drift bug.
        if is_permanent_failure(exception):
            return None
        # job.attempts is the count of attempts already made (1-based after the first).
        idx = job.attempts - 1
        if idx >= len(_SCHEDULE_SECONDS):
            return None  # exhausted → dead-letter (procrastinate 3.x: None = no retry)
        return RetryDecision(retry_in={"seconds": _SCHEDULE_SECONDS[idx]})
