"""Killable CPU boundary for untrusted scan inputs, with unchanged stdlib rules.

Pickle is private IPC only: the parent constructs the request from its bounded
file index, and accepts a response only from the Python child it launches. No
network body, artifact bytes, or external file is ever treated as a pickle.
"""

from __future__ import annotations

import asyncio
import contextlib
import pickle  # nosec B403
import sys
from typing import TYPE_CHECKING, Literal, cast

if TYPE_CHECKING:
    from app.scan.engine import RepoScanResult, ScanResult

SCORING_TIMEOUT_SECONDS = 30.0
_REAP_TIMEOUT_SECONDS = 5.0
_REAPERS: set[asyncio.Task[None]] = set()


class ScanEvaluationTimeout(ValueError):
    """A bounded evaluation failed, so no partial verdict may be published.

    ValueError keeps this deterministic input failure out of the worker's
    transient-error retry path.
    """


class ScanEvaluationError(ValueError):
    """The child reported a deterministic error without disclosing its input."""


async def _reap(process: asyncio.subprocess.Process) -> None:
    # communicate drains pipe buffers as well as reaping: wait() alone can hang
    # after cancellation when a full stdout pipe has paused its transport.
    await asyncio.wait_for(process.communicate(), timeout=_REAP_TIMEOUT_SECONDS)


def _reaper_finished(task: asyncio.Task[None]) -> None:
    _REAPERS.discard(task)
    if not task.cancelled():
        task.exception()  # consume an error if the caller was cancelled again


async def score_in_process(
    file_index: list[tuple[str, bytes]],
    rubric_version: str,
    ref_sha: str,
    *,
    mode: Literal["single", "repo"] = "repo",
    kind: str | None = None,
    source_kind: str | None = None,
) -> ScanResult | RepoScanResult:
    """Score one repository while its parent's event loop remains available.

    The wall deadline includes startup and both IPC directions, not just regex
    matching. asyncio owns process creation: cancellation during spawn closes
    and waits for its subprocess transport before propagating. Once returned,
    we own the child and kill/reap it on timeout, cancellation, or failure.
    """
    process: asyncio.subprocess.Process | None = None
    try:
        async with asyncio.timeout(SCORING_TIMEOUT_SECONDS):
            request = await asyncio.to_thread(
                pickle.dumps,
                (mode, file_index, rubric_version, ref_sha, kind, source_kind),
                pickle.HIGHEST_PROTOCOL,
            )
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "app.scan.scoring_process",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                # Never expose a child exception containing artifact text.
                stderr=asyncio.subprocess.DEVNULL,
            )
            output, _ = await process.communicate(request)
            if process.returncode != 0:
                raise RuntimeError("Scoring process exited without a result")
            try:
                # Only this owned child's stdout is deserialized, not artifacts.
                response = await asyncio.to_thread(pickle.loads, output)
            except Exception:
                raise RuntimeError("Scoring process returned an invalid result") from None

            from app.scan.engine import RepoScanResult, ScanResult

            if not isinstance(response, tuple) or len(cast(tuple[object, ...], response)) != 2:
                raise RuntimeError("Scoring process returned an invalid result")
            status, value = cast(tuple[str, object], response)
            if status == "error" and value == "permanent":
                raise ScanEvaluationError("Scan evaluation failed")
            if status == "error" and value == "unknown":
                raise RuntimeError("Scoring process failed")
            expected = ScanResult if mode == "single" else RepoScanResult
            if status != "ok" or not isinstance(value, expected):
                raise RuntimeError("Scoring process returned an invalid result")
            return value
    except TimeoutError:
        raise ScanEvaluationTimeout("Scan evaluation exceeded its time budget") from None
    finally:
        if process is not None:
            primary_error = sys.exception()
            if process.returncode is None:
                # The child may have exited since the returncode check.
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
            cleanup = asyncio.create_task(_reap(process))
            # Keep cleanup alive even if a second cancellation interrupts the
            # caller. The kill above is synchronous; this task drains/reaps it.
            _REAPERS.add(cleanup)
            cleanup.add_done_callback(_reaper_finished)
            try:
                await asyncio.shield(cleanup)
            except Exception:
                if primary_error is None:
                    raise RuntimeError("Scoring process cleanup failed") from None


def _main() -> None:
    from app.ingestion.framework.retry import is_permanent_failure
    from app.scan import engine

    # This pipe is supplied solely by score_in_process, never by an HTTP caller.
    mode, file_index, rubric_version, ref_sha, kind, source_kind = cast(
        tuple[str, list[tuple[str, bytes]], str, str, str | None, str | None],
        pickle.loads(sys.stdin.buffer.read()),  # nosec B301
    )
    try:
        if mode == "single":
            result = engine.score_single_file_index(file_index, rubric_version, ref_sha, kind=kind)
        elif mode == "repo":
            result = engine.run_repo_scan_from_index(
                file_index, rubric_version, ref_sha=ref_sha, source_kind=source_kind
            )
        else:
            raise ValueError("Unknown scoring mode")
        response = ("ok", result)
    except Exception as exc:
        # Preserve retry classification, but never forward exception messages,
        # frames, paths, or artifact content through the error envelope.
        response = ("error", "permanent" if is_permanent_failure(exc) else "unknown")
    sys.stdout.buffer.write(pickle.dumps(response, protocol=pickle.HIGHEST_PROTOCOL))


if __name__ == "__main__":
    _main()
