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

import app.observability.events as events
from app.observability.events import _BACKEND_DISTINCT_ID


def test_emit_calls_capture_with_posthog_7x_keyword_signature(monkeypatch) -> None:
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


def test_emit_is_a_noop_when_client_unset(monkeypatch) -> None:
    """No PostHog client → structlog-only, never an attribute error."""
    monkeypatch.setattr(events, "_posthog_client", None)
    events.emit_scan_started(scan_id="abc-123")  # must not raise
