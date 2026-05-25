"""Test fixtures and JSON shape assertions.

Small, focused helpers. Adding domain-specific fixtures (event
envelopes, seed payloads) here keeps them out of command files where
they would obscure the test flow.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


class FixtureError(AssertionError):
    """Raised by `assert_*` helpers when a shape contract regresses."""


def assert_json_has_keys(body: object, keys: Iterable[str]) -> dict[str, Any]:
    """Assert `body` is a JSON object containing every key in `keys`.

    Returns the body cast to `dict[str, Any]` so callers can index it
    without re-narrowing. Missing keys raise `FixtureError` with a
    message naming every absent key so a single failure surfaces the
    full diff.
    """
    if not isinstance(body, dict):
        raise FixtureError(f"expected JSON object, got {type(body).__name__}")
    typed: dict[str, Any] = body  # pyright: ignore[reportUnknownVariableType]
    missing = [k for k in keys if k not in typed]
    if missing:
        raise FixtureError(f"missing keys: {missing!r}; got keys {sorted(typed.keys())!r}")
    return typed


def assert_json_value(body: dict[str, Any], key: str, expected: object) -> None:
    """Assert `body[key] == expected`.

    Used for the OpenAPI title check (`info.title == "SaferSkills API"`)
    and the health body check (`status == "ok"`). Keeps the assertion
    failure message uniform across commands.
    """
    actual = body.get(key)
    if actual != expected:
        raise FixtureError(
            f"expected {key}={expected!r}, got {actual!r}"
        )
