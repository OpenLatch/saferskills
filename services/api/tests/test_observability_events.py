"""Regression tests for the backend PostHog emit path (`app.observability.events`).

The bug: a Dependabot bump to `posthog`(-python) 7.x changed `Client.capture()`
to `capture(event, *, distinct_id=…, properties=…)` (event is the 1st positional;
distinct_id/properties are keyword-only). `_emit` still called the pre-3.x
positional form `client.capture(distinct_id, event, props)`, which raises
`TypeError: capture() takes 2 positional arguments but 4 were given` — silently
swallowed by `_emit`'s `except`, so every backend PostHog event was lost.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import app.observability.events as events
from app.observability.events import _BACKEND_DISTINCT_ID  # pyright: ignore[reportPrivateUsage]


def test_emit_calls_capture_with_posthog_7x_keyword_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    monkeypatch.setattr(events, "_posthog_client", client)

    events.emit_scan_started(scan_id="abc-123")

    # event is the sole positional arg; distinct_id + properties are keyword-only
    # (posthog-python 7.x). The pre-fix positional call would make this assertion
    # fail (and against a real client, raise TypeError).
    client.capture.assert_called_once()
    args, kwargs = client.capture.call_args
    assert args == ("scan_started",)
    assert kwargs["distinct_id"] == _BACKEND_DISTINCT_ID
    assert kwargs["properties"]["product"] == "saferskills"
    assert kwargs["properties"]["$process_person_profile"] is False


def test_emit_is_a_noop_when_client_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """No PostHog client → structlog-only, never an attribute error."""
    monkeypatch.setattr(events, "_posthog_client", None)
    events.emit_scan_started(scan_id="abc-123")  # must not raise


# ─── Capability / agent-run share-token redaction ───

_TOK = "Hh3y6Qk2pN8fT0aZ1cV9bWx"


@pytest.mark.parametrize(
    "prefix",
    ["/scans/r/", "/agents/r/", "/api/v1/agent-scans/r/"],
)
def test_redact_capability_token_covers_every_unlisted_route(prefix: str) -> None:
    """The possession-is-auth token must be redacted for the scan capability URL,
    the Agent Report PAGE URL (/agents/r/), AND the API (/agent-scans/r/)."""
    url = f"https://saferskills.ai{prefix}{_TOK}?ref=x"
    redacted = events.redact_capability_token(url)
    assert _TOK not in redacted
    assert f"{prefix}<redacted>" in redacted


def test_redact_does_not_touch_the_public_agent_report_url() -> None:
    """A public `/agents/{id}` page URL carries no secret — it must NOT be rewritten."""
    url = "https://saferskills.ai/agents/018e7c8b-aaaa-7000-8000-000000000001"
    assert events.redact_capability_token(url) == url


def test_scrub_sentry_event_redacts_agent_token_in_request_and_breadcrumbs() -> None:
    event: dict[str, object] = {
        "request": {"url": f"https://saferskills.ai/agents/r/{_TOK}"},
        "breadcrumbs": {"values": [{"category": "navigation", "data": f"GET /agents/r/{_TOK}"}]},
    }
    scrubbed = events.scrub_sentry_event(event)
    assert scrubbed is not None
    assert _TOK not in str(scrubbed)
