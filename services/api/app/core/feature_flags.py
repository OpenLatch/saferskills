"""Server-side feature flags — a thin wrapper over the PostHog client.

PostHog evaluates flags one of two ways:
  - **Local** (no network per check) when a personal API key (`posthog_server_
    key`) was supplied to the client constructor — PostHog loads the flag
    definitions in the background and evaluates them in-process.
  - **Remote** (`/decide`) otherwise, using the project key.
Both are transparent here — the same `client.feature_enabled(...)` call works.

Flag names are a CLOSED, reviewed set (mirrors the closed-enum discipline in
`.claude/rules/telemetry.md`): adding a flag is a reviewed change here, never an
arbitrary string at a call site. At launch exactly ONE example flag exists and
nothing real is gated by it — it only proves the wiring end-to-end.

Every helper degrades to its `default` when PostHog is unconfigured (dev/test/
CI) or any error occurs — a flag lookup must never break a request.
"""

from typing import Final

import structlog

from app.observability.events import get_posthog_client

logger = structlog.get_logger(__name__)

# ─── Closed flag set ──────────────────────────────────────────────────────────
# The single launch example. Nothing is gated by it; it exists so the flag path
# is exercised + documented. Real flags are added here in a reviewed PR.
EXAMPLE_FLAG: Final = "saferskills-example-flag"


def is_enabled(flag: str, distinct_id: str, *, default: bool = False) -> bool:
    """Whether `flag` is enabled for `distinct_id`. `default` on disabled/error."""
    client = get_posthog_client()
    if client is None:
        return default
    try:
        result = client.feature_enabled(flag, distinct_id)
        return default if result is None else bool(result)
    except Exception:  # a flag lookup must never break a request
        logger.warning("feature_flags.eval_failed", flag=flag)
        return default


def get_payload(flag: str, distinct_id: str, *, default: object | None = None) -> object | None:
    """The JSON payload attached to `flag` for `distinct_id`. `default` on miss/error."""
    client = get_posthog_client()
    if client is None:
        return default
    try:
        payload = client.get_feature_flag_payload(flag, distinct_id)
        return default if payload is None else payload
    except Exception:  # a flag lookup must never break a request
        logger.warning("feature_flags.payload_failed", flag=flag)
        return default
