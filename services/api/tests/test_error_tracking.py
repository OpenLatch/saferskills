"""Privacy and delivery regression tests for server error tracking."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterator
from typing import Any, Literal
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel, Field, ValidationError

from app.observability import errors, events


class _CymbalPythonFrame(BaseModel):
    """Required raw-frame wire contract, independent of our privacy projection.

    PostHog's rust/cymbal/src/core/types/frames/mod.rs tags RawFrame by
    `platform`; langs/python.rs requires filename/function and accepts an
    optional u32 lineno. Remaining Python fields are optional/defaulted.
    https://github.com/PostHog/posthog/tree/master/rust/cymbal/src/core/types
    """

    platform: Literal["python"]
    filename: str
    function: str
    lineno: int | None = Field(default=None, ge=0, le=2**32 - 1)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[MagicMock]:
    from posthog import Posthog

    client = MagicMock()

    def record(event: dict[str, Any]) -> dict[str, Any] | None:
        safe = errors.before_send(event)
        if safe is not None:
            client.capture(
                safe["event"], distinct_id=safe["distinct_id"], properties=safe["properties"]
            )
        return safe

    sdk = Posthog(
        project_api_key="phc_test",
        send=False,
        before_send=record,
        enable_exception_autocapture=False,
        capture_exception_code_variables=False,
        privacy_mode=True,
    )
    client.capture_exception.side_effect = sdk.capture_exception
    monkeypatch.setattr(events, "_posthog_client", client)
    monkeypatch.setattr(
        events,
        "_event_metadata",
        {
            "product": "saferskills",
            "environment": "staging",
            "service": "worker",
            "release": "abc123",
        },
    )
    yield client
    sdk.shutdown()


def _payload(client: MagicMock) -> dict[str, Any]:
    args, kwargs = client.capture.call_args
    assert args == ("$exception",)
    assert kwargs["distinct_id"] == "saferskills-backend"
    return kwargs["properties"]


def test_exception_messages_chains_locals_and_paths_never_leave(client: MagicMock) -> None:
    secret = "https://saferskills.ai/agents/r/private-token?secret=abc"
    try:
        try:
            raise ValueError(secret)
        except ValueError as cause:
            raise RuntimeError("uploaded secret document") from cause
    except RuntimeError as exc:
        errors.capture_exception(exc, context="scan")
        errors.capture_exception(exc, context="job")
    client.capture.assert_called_once()
    props = _payload(client)
    serialized = json.dumps(props)
    assert secret not in serialized
    assert "uploaded" not in serialized
    assert "test_error_tracking" not in serialized
    assert {item["type"] for item in props["$exception_list"]} == {"RuntimeError", "ValueError"}
    assert props["environment"] == "staging"
    assert props["service"] == "worker"
    assert props["release"] == "abc123"
    assert props["$process_person_profile"] is False


def test_retains_application_stack_locations_without_source(client: MagicMock) -> None:
    from app.core.config import coerce_ssl_to_sslmode

    try:
        coerce_ssl_to_sslmode(None)  # pyright: ignore[reportArgumentType]
    except Exception as exc:
        errors.capture_exception(exc, context="startup")
    frames = _payload(client)["$exception_list"][0]["stacktrace"]["frames"]
    assert frames
    assert frames[-1]["filename"] == "app/core/config.py"
    assert frames[-1]["function"] == "coerce_ssl_to_sslmode"
    assert set(frames[-1]) == {"platform", "filename", "function", "lineno", "in_app"}
    for frame in frames:
        _CymbalPythonFrame.model_validate(frame)
    # A valid ingestion response does not imply successful error processing.
    # This reproduces Cymbal's rejection of the previously emitted payload.
    missing_platform = {key: value for key, value in frames[-1].items() if key != "platform"}
    with pytest.raises(ValidationError, match="platform"):
        _CymbalPythonFrame.model_validate(missing_platform)


def test_sdk_boundary_recursively_redacts_and_rebuilds_error_schema() -> None:
    raw: dict[str, Any] = {
        "event": "$exception",
        "properties": {
            "product": "saferskills",
            "request": {"headers": {"Authorization": "private"}},
            "arbitrary": "secret artifact bytes",
            "error_context": "scan",
            "$exception_list": [
                {
                    "type": "ValueError",
                    "value": "raw secret",
                    "extra": {"user": "private"},
                    "stacktrace": {
                        "frames": [
                            {
                                "filename": "app/scan/engine.py",
                                "function": "scan",
                                "lineno": 42,
                                "vars": {"secret": "private"},
                                "context_line": "uploaded",
                                "arbitrary": "secret",
                            },
                            {"filename": "/home/customer/private.py", "lineno": 1},
                        ]
                    },
                }
            ],
        },
    }
    safe = errors.before_send(raw)
    assert safe is not None
    serialized = json.dumps(safe)
    assert all(
        secret not in serialized for secret in ["private", "uploaded", "raw secret", "arbitrary"]
    )
    assert "app/scan/engine.py" in serialized
    assert raw["properties"]["$exception_list"][0]["value"] == "raw secret"


def test_scrubber_fails_closed_for_invalid_or_cyclic_input() -> None:
    cyclic: dict[str, Any] = {}
    cyclic["cycle"] = cyclic
    assert errors.before_send(cyclic) is None
    assert errors.before_send({"event": "$exception", "properties": {}}) is None
    assert errors.before_send({"unserializable": object()}) is None


def test_product_event_keeps_existing_closed_enum_source() -> None:
    result = errors.before_send(
        {
            "event": "ingestion_cycle_failed",
            "properties": {
                "source": "mcp_registry",
                "reason_enum": "timeout",
                "nested": {"token": "private", "value": "https://private.invalid"},
            },
        }
    )
    assert result is not None
    assert result["properties"]["source"] == "mcp_registry"
    assert "private" not in json.dumps(result)


@pytest.mark.asyncio
async def test_http_error_is_reported_and_response_behavior_preserved(client: MagicMock) -> None:
    app = FastAPI()
    app.add_middleware(errors.ErrorCaptureMiddleware)

    @app.get("/fault")
    async def fault() -> None:  # pyright: ignore[reportUnusedFunction]
        raise ValueError("private request data")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as http:
        response = await http.get(
            "/fault?token=private", headers={"Authorization": "Bearer private"}
        )
        missing = await http.get("/not-found")
    assert response.status_code == 500
    assert missing.status_code == 404
    client.capture.assert_called_once()
    assert _payload(client)["error_context"] == "http"
    assert "private" not in json.dumps(_payload(client))


def test_job_bridge_captures_retries_without_job_arguments(client: MagicMock) -> None:
    logger = logging.getLogger("procrastinate.worker")
    parent = logging.getLogger("procrastinate")
    old_handlers = parent.handlers[:]
    old_level = logger.level
    try:
        errors.install_job_error_capture()
        errors.install_job_error_capture()
        logger.setLevel(logging.INFO)
        try:
            raise ValueError("secret job arguments")
        except ValueError:
            logger.info("retry job containing secret-url", exc_info=True)
        client.capture.assert_called_once()
        assert _payload(client)["error_context"] == "job"
        assert "secret" not in json.dumps(_payload(client))
    finally:
        parent.handlers[:] = old_handlers
        logger.setLevel(old_level)


@pytest.mark.asyncio
async def test_worker_reports_a_failing_job_once_not_per_retry(client: MagicMock) -> None:
    """Real Procrastinate worker: a job failing on every attempt (retry=3 -> 4 runs)
    is reported to PostHog once, at the terminal failure, not on each retried run."""
    from procrastinate import App, RetryStrategy
    from procrastinate.testing import InMemoryConnector

    app = App(connector=InMemoryConnector())
    runs: list[int] = []

    @app.task(name="always_failing", retry=RetryStrategy(max_attempts=3, wait=0))
    async def always_failing() -> None:
        runs.append(1)
        raise ConnectionError("blip")

    parent = logging.getLogger("procrastinate")
    old_handlers, old_level = parent.handlers[:], parent.level
    try:
        errors.install_job_error_capture()
        parent.setLevel(logging.INFO)
        async with app.open_async():
            await always_failing.defer_async()
            await app.run_worker_async(wait=False, install_signal_handlers=False)
        assert len(runs) == 4
        client.capture.assert_called_once()
        assert _payload(client)["error_context"] == "job"
    finally:
        parent.handlers[:] = old_handlers
        parent.setLevel(old_level)


@pytest.mark.asyncio
async def test_ingestion_cycle_bug_is_reported_once_across_retries(
    client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real ingestion task wrapper under a real Procrastinate worker: an unexpected
    cycle error re-raises into the IngestionRetry schedule on every attempt. The
    failure is reported once (terminal job_error), not once per attempt plus once."""
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock

    from procrastinate.testing import InMemoryConnector

    from app.core import config as config_module
    from app.db import session as session_module
    from app.ingestion import procrastinate_app, tasks
    from app.ingestion.config.loader import get_source_config
    from app.ingestion.framework import retry
    from app.ingestion.sources.smithery import SmitheryAdapter

    monkeypatch.setattr(config_module.get_settings(), "ingestion_source_blocklist", [])
    monkeypatch.setattr(retry, "_SCHEDULE_SECONDS", (0, 0, 0, 0))
    adapter = SmitheryAdapter(get_source_config("smithery"))

    async def _boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("bug")  # a fresh exception object per attempt, as in prod

    adapter.run_cycle = AsyncMock(side_effect=_boom)  # type: ignore[method-assign]
    monkeypatch.setattr(tasks, "build_adapter", lambda _name: adapter)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    monkeypatch.setattr(tasks, "is_source_paused", AsyncMock(return_value=False))
    monkeypatch.setattr(tasks, "record_run_started", AsyncMock(return_value=None))
    monkeypatch.setattr(tasks, "record_run_finished", AsyncMock())

    @asynccontextmanager
    async def _session():  # type: ignore[no-untyped-def]
        yield MagicMock()

    monkeypatch.setattr(session_module, "AsyncSessionLocal", _session)

    parent = logging.getLogger("procrastinate")
    old_handlers, old_level = parent.handlers[:], parent.level
    try:
        errors.install_job_error_capture()
        parent.setLevel(logging.INFO)
        with procrastinate_app.replace_connector(InMemoryConnector()):
            async with procrastinate_app.open_async():
                await procrastinate_app.tasks["ingest_cycle_smithery"].defer_async(timestamp=0)  # pyright: ignore[reportUnknownMemberType]
                await procrastinate_app.run_worker_async(wait=False, install_signal_handlers=False)
        assert adapter.run_cycle.await_count > 1  # retried
        # Other periodic jobs on the shared queue may fail on the fake session;
        # only the cycle's own RuntimeError matters here.
        contexts = [
            c.kwargs["properties"]["error_context"]
            for c in client.capture.call_args_list
            if c.args[0] == "$exception"
            and c.kwargs["properties"]["$exception_list"][0]["type"] == "RuntimeError"
        ]
        assert contexts == ["job"]
    finally:
        parent.handlers[:] = old_handlers
        parent.setLevel(old_level)


def test_disabled_cancelled_and_broken_transport_never_raise(
    client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    errors.capture_exception(asyncio.CancelledError(), context="job")
    client.capture.assert_not_called()
    client.capture.side_effect = RuntimeError("offline")
    errors.capture_exception(ValueError("private"), context="scan")
    monkeypatch.setattr(events, "_posthog_client", None)
    errors.capture_exception(ValueError("private"), context="scan")


def test_development_never_initializes_network_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(events, "_posthog_client", None)
    events.init_posthog(project_key="phc_example", host="https://eu.i.posthog.com")
    assert events.get_posthog_client() is None


def test_client_uses_privacy_boundary_and_explicit_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    import posthog

    constructor = MagicMock()
    monkeypatch.setattr(posthog, "Posthog", constructor)
    monkeypatch.setattr(events, "_posthog_client", None)
    monkeypatch.setattr(events, "_event_metadata", {})
    events.init_posthog(
        project_key="phc_example",
        host="https://eu.i.posthog.com",
        environment="staging",
        service="worker",
        release="abc123",
    )
    options = constructor.call_args.kwargs
    assert options["before_send"] is errors.before_send
    assert options["enable_exception_autocapture"] is False
    assert options["capture_exception_code_variables"] is False
    assert options["privacy_mode"] is True
    events.emit_scan_started(scan_id="private")
    props = constructor.return_value.capture.call_args.kwargs["properties"]
    assert props["service"] == "worker"
    assert props["environment"] == "staging"
    assert props["release"] == "abc123"


def test_shutdown_uses_daemon_and_finite_join(
    client: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    thread = MagicMock()
    monkeypatch.setattr(events.threading, "Thread", thread)
    events.shutdown_posthog()
    assert events.get_posthog_client() is None
    assert thread.call_args.kwargs["daemon"] is True
    thread.return_value.start.assert_called_once()
    thread.return_value.join.assert_called_once_with(timeout=4.0)
