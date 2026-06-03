"""Escalating retry schedule for ingestion tasks (D-04-03: 1m → 5m → 30m → 6h).

Procrastinate's built-in RetryStrategy only does constant / linear / exponential
backoff, none of which matches the plan's 1m/5m/30m/6h schedule. A tiny custom
BaseRetryStrategy gives the exact schedule, then dead-letters (max 4 attempts).
"""

from __future__ import annotations

from procrastinate import BaseRetryStrategy, RetryDecision
from procrastinate.jobs import Job

_SCHEDULE_SECONDS = (60, 300, 1800, 21600)  # 1m, 5m, 30m, 6h


class IngestionRetry(BaseRetryStrategy):
    max_attempts = len(_SCHEDULE_SECONDS)

    def get_retry_decision(self, *, exception: BaseException, job: Job) -> RetryDecision | None:
        # job.attempts is the count of attempts already made (1-based after the first).
        idx = job.attempts - 1
        if idx >= len(_SCHEDULE_SECONDS):
            return None  # exhausted → dead-letter (procrastinate 3.x: None = no retry)
        return RetryDecision(retry_in={"seconds": _SCHEDULE_SECONDS[idx]})
