"""Privacy-safe error tracking for HTTP, background tasks, and caught failures.

Only exception classes and our own code locations leave this process. Exception
messages, request metadata, source lines, locals, and third-party paths can all
contain submitted artifacts or credentials and are deliberately omitted.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Literal, cast

from starlette.types import ASGIApp, Receive, Scope, Send

from app.observability import events

_APP_ROOT = Path(__file__).resolve().parents[1]
_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.<>]{0,199}$")
_METADATA_KEYS = frozenset(
    {
        "product",
        "environment",
        "service",
        "release",
        "$app_version",
        "$process_person_profile",
        "$lib",
        "$lib_version",
        "$is_server",
    }
)
type ErrorContext = Literal[
    "http",
    "ingestion",
    "scan",
    "job",
    "startup",
    "sweep",
    "slack_invite",
    "database_pool",
    "database_statement",
]
_CONTEXTS = frozenset(
    {
        "http",
        "ingestion",
        "scan",
        "job",
        "startup",
        "sweep",
        "slack_invite",
        "database_pool",
        "database_statement",
    }
)


def _identifier(value: object) -> str:
    return value if isinstance(value, str) and _IDENTIFIER.fullmatch(value) else "unknown"


def _scrub(value: object, *, depth: int = 0) -> object:
    """Recursively scrub forbidden fields; reject unknown objects/cycles.

    This final SDK boundary also protects future emitters. Error messages and
    payloads are dropped wholesale, rather than relying on secret regexes.
    """
    if depth > 20:
        raise ValueError("telemetry nesting limit")
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if re.search(
            r"https?://|[\\]|@|/(?:scans|agents|agent-scans)/r/|(?i:bearer\s|phx_|ghp_|sk-)", value
        ):
            return "[redacted]"
        return value[:500]
    if isinstance(value, list):
        return [_scrub(v, depth=depth + 1) for v in cast(list[object], value)[:100]]
    if isinstance(value, dict):
        return {
            key: _scrub(item, depth=depth + 1)
            for key, item in cast(dict[object, object], value).items()
            if isinstance(key, str)
            and key.lower()
            not in {
                "request",
                "headers",
                "cookies",
                "body",
                "data",
                "extra",
                "user",
                "vars",
                "locals",
                "context_line",
                "pre_context",
                "post_context",
                "message",
                "password",
                "authorization",
                "token",
                "share_token",
                "submit_token",
                "content",
                "matched_content",
                "url",
                "ip",
                "email",
            }
        }
    raise ValueError("unsupported telemetry value")


def before_send(event: dict[str, Any]) -> dict[str, Any] | None:
    """Fail closed: an event that cannot be sanitized never reaches the network."""
    try:
        if event.get("event") == "$exception":
            props = event["properties"]
            # Project the SDK exception schema onto privacy-safe fields only.
            exceptions: list[dict[str, object]] = []
            for exc in props["$exception_list"][:10]:
                frames: list[dict[str, object]] = []
                for frame in exc.get("stacktrace", {}).get("frames", [])[-50:]:
                    raw_filename = frame.get("abs_path") or frame.get("filename", "")
                    if not isinstance(raw_filename, str):
                        continue
                    if raw_filename.startswith("app/"):
                        filename = raw_filename
                    else:
                        try:
                            filename = (
                                "app/"
                                + Path(raw_filename).resolve().relative_to(_APP_ROOT).as_posix()
                            )
                        except ValueError:
                            continue
                    if not re.fullmatch(r"app/[a-zA-Z0-9_/.-]+\.py", filename) or ".." in filename:
                        continue
                    if type(frame.get("lineno")) is not int:
                        continue
                    frames.append(
                        {
                            "filename": filename,
                            "function": _identifier(frame.get("function")),
                            "lineno": frame["lineno"],
                            "in_app": True,
                        }
                    )
                name = _identifier(exc.get("type"))
                mechanism = exc.get("mechanism", {})
                safe_mechanism: dict[str, object] = {
                    "type": "chained" if mechanism.get("type") == "chained" else "generic",
                    "handled": props.get("error_context") != "http",
                }
                for key in ("exception_id", "parent_id"):
                    if type(mechanism.get(key)) is int:
                        safe_mechanism[key] = mechanism[key]
                if mechanism.get("is_exception_group") is True:
                    safe_mechanism["is_exception_group"] = True
                exceptions.append(
                    {
                        "type": name,
                        "value": name,
                        "mechanism": safe_mechanism,
                        "stacktrace": {"type": "raw", "frames": frames},
                    }
                )
            event = {
                **event,
                "properties": {
                    **{key: props[key] for key in _METADATA_KEYS if key in props},
                    "$exception_list": exceptions,
                    "error_context": props.get("error_context")
                    if props.get("error_context") in _CONTEXTS
                    else "job",
                    "$process_person_profile": False,
                    "$geoip_disable": True,
                },
            }
        return cast(dict[str, Any], _scrub(event))
    except Exception:
        return None


def capture_exception(error: BaseException, *, context: ErrorContext) -> None:
    """Report an exception once, never allowing telemetry to affect control flow."""
    client = events.get_posthog_client()
    if client is None or not isinstance(error, Exception):
        return
    try:
        if getattr(error, "_saferskills_reported", False):
            return
        properties = {
            **events._event_metadata,  # pyright: ignore[reportPrivateUsage]
            "error_context": context,
            "$process_person_profile": False,
        }
        client.capture_exception(error, distinct_id="saferskills-backend", properties=properties)
        error._saferskills_reported = True  # pyright: ignore[reportAttributeAccessIssue]
    except Exception:
        pass


class ErrorCaptureMiddleware:
    """ASGI wrapper retains streaming/error semantics and never exports requests."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await self.app(scope, receive, send)
        except Exception as exc:
            capture_exception(exc, context="http")
            raise


class _JobErrorHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # Procrastinate attaches exc_info to both terminal and retried job logs.
        # Ignore its message, args, and extra: they contain job arguments.
        if record.exc_info and isinstance(record.exc_info[1], Exception):
            capture_exception(record.exc_info[1], context="job")


def install_job_error_capture() -> None:
    logger = logging.getLogger("procrastinate")
    if not any(isinstance(handler, _JobErrorHandler) for handler in logger.handlers):
        logger.addHandler(_JobErrorHandler())
