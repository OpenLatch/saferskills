"""Real subprocess lifecycle gates for the CPU scoring boundary."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import pytest

from app.ingestion.framework.retry import is_permanent_failure
from app.scan import scoring_process


def _replace_child(
    monkeypatch: pytest.MonkeyPatch, code: str, *, cancel_after_spawn: bool = False
) -> list[asyncio.subprocess.Process]:
    original = asyncio.create_subprocess_exec
    children: list[asyncio.subprocess.Process] = []

    async def spawn(*args: Any, **kwargs: Any) -> asyncio.subprocess.Process:
        child = await original(sys.executable, "-c", code, **kwargs)
        children.append(child)
        if cancel_after_spawn:
            current = asyncio.current_task()
            assert current is not None
            current.cancel()
        return child

    monkeypatch.setattr(scoring_process.asyncio, "create_subprocess_exec", spawn)
    return children


async def test_deadline_includes_blocked_input_and_reaps_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    children = _replace_child(monkeypatch, "import time; time.sleep(60)")
    monkeypatch.setattr(scoring_process, "SCORING_TIMEOUT_SECONDS", 0.2)
    # Larger than a pipe buffer; the child never reads it.
    with pytest.raises(scoring_process.ScanEvaluationTimeout):
        await scoring_process.score_in_process([("large.md", b"x" * 2_000_000)], "test", "a" * 40)
    assert len(children) == 1
    assert children[0].returncode is not None


async def test_cancel_with_large_child_output_drains_and_reaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    children = _replace_child(
        monkeypatch,
        "import sys,time; sys.stdin.buffer.read(); "
        "sys.stdout.buffer.write(b'x'*4_000_000); sys.stdout.buffer.flush(); time.sleep(60)",
    )
    task = asyncio.create_task(scoring_process.score_in_process([], "test", "a" * 40))
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=3)
    assert len(children) == 1
    assert children[0].returncode is not None


async def test_cancellation_at_spawn_return_does_not_orphan_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    children = _replace_child(monkeypatch, "import time; time.sleep(60)", cancel_after_spawn=True)
    with pytest.raises(asyncio.CancelledError):
        await scoring_process.score_in_process([], "test", "a" * 40)
    assert len(children) == 1
    assert children[0].returncode is not None


async def test_deadline_also_cancels_pending_spawn(monkeypatch: pytest.MonkeyPatch) -> None:
    cancelled = False

    async def spawn(*args: Any, **kwargs: Any) -> asyncio.subprocess.Process:
        nonlocal cancelled
        try:
            await asyncio.sleep(60)
        finally:
            cancelled = True
        raise AssertionError("spawn must be cancelled")

    monkeypatch.setattr(scoring_process.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(scoring_process, "SCORING_TIMEOUT_SECONDS", 0.05)
    with pytest.raises(scoring_process.ScanEvaluationTimeout):
        await scoring_process.score_in_process([], "test", "a" * 40)
    assert cancelled


@pytest.mark.parametrize(
    "code,message",
    [
        ("import sys; sys.exit(7)", "exited without a result"),
        (
            "import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write(b'private contents')",
            "invalid result",
        ),
        (
            "import sys,pickle; sys.stdin.buffer.read(); "
            "sys.stdout.buffer.write(pickle.dumps(('ok', 'private contents')))",
            "invalid result",
        ),
    ],
)
async def test_early_exit_and_malformed_response_fail_safely(
    monkeypatch: pytest.MonkeyPatch, code: str, message: str
) -> None:
    children = _replace_child(monkeypatch, code)
    with pytest.raises(RuntimeError, match=message) as caught:
        await scoring_process.score_in_process([], "test", "a" * 40)
    assert "private contents" not in str(caught.value)
    assert children[0].returncode is not None


@pytest.mark.parametrize("category,permanent", [("permanent", True), ("unknown", False)])
async def test_safe_child_failure_preserves_retry_category(
    monkeypatch: pytest.MonkeyPatch, category: str, permanent: bool
) -> None:
    children = _replace_child(
        monkeypatch,
        "import sys,pickle; sys.stdin.buffer.read(); "
        f"sys.stdout.buffer.write(pickle.dumps(('error', '{category}')))",
    )
    with pytest.raises((scoring_process.ScanEvaluationError, RuntimeError)) as caught:
        await scoring_process.score_in_process([], "test", "a" * 40)
    assert is_permanent_failure(caught.value) is permanent
    assert children[0].returncode is not None


async def test_cleanup_failure_does_not_mask_scan_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    children = _replace_child(monkeypatch, "import time; time.sleep(60)")
    monkeypatch.setattr(scoring_process, "SCORING_TIMEOUT_SECONDS", 0.1)
    original = scoring_process._reap  # pyright: ignore[reportPrivateUsage]

    async def failed_reap(process: asyncio.subprocess.Process) -> None:
        await original(process)
        raise TimeoutError("simulated cleanup deadline")

    monkeypatch.setattr(scoring_process, "_reap", failed_reap)
    with pytest.raises(scoring_process.ScanEvaluationTimeout) as caught:
        await scoring_process.score_in_process([], "test", "a" * 40)
    assert is_permanent_failure(caught.value)
    assert children[0].returncode is not None
