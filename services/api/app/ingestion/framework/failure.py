"""Shared failure taxonomy — maps an exception to a bucketed `reason_enum`.

Robustness overhaul (WS-4): promoted from the private `tasks._classify_cycle_
failure` so BOTH the ingestion cycle wrapper (`tasks.run_source_cycle`) AND the
durable scan path (`tasks_scan`) classify failures the same way — one WARN
vocabulary, one closed `reason_enum`, no duplicate logic that can drift.

`classify_failure(exc) -> IngestionFailureReason`:
  - `timeout`    — `httpx.TimeoutException`
  - `rate_limit` — a 403/429 `HTTPStatusError` (GitHub signals rate limit with 403)
  - `http_5xx`   — a 5xx `HTTPStatusError`
  - `permanent`  — deterministic shape-drift / programming error (see retry.py):
                   retrying re-fails, so the caller must NOT re-raise these.
  - `other`      — anything else (DNS/connection error, OSError, unknown).

`cf_challenge` is NOT produced here — it is handled by the dedicated
`AdapterBlockedError` branch upstream (the Cloudflare terminal path).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from app.ingestion.framework.retry import is_permanent_failure

if TYPE_CHECKING:
    from app.observability.events import IngestionFailureReason


def classify_failure(exc: BaseException) -> IngestionFailureReason:
    """Map a provider/transport/shape-drift failure to the closed `reason_enum`."""
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (403, 429):
            return "rate_limit"
        if 500 <= code < 600:
            return "http_5xx"
    if is_permanent_failure(exc):
        return "permanent"
    return "other"


def is_transient_failure(exc: BaseException) -> bool:
    """True when a retry could plausibly clear the failure (transport/5xx/timeout/
    rate-limit/unknown). The scan path re-raises ONLY these so Procrastinate retries
    genuine blips and never a permanent shape-drift bug."""
    return not is_permanent_failure(exc)
