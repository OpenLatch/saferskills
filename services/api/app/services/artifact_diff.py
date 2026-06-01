"""Line-level diffs between two stored scan snapshots.

Loads the `{path -> bytes|None}` snapshot for each scan from `scans.file_hashes`
+ `artifact_blobs`, then diffs the two with stdlib `difflib` into a structured
shape the item-page diff panel renders (files → hunks → lines).

Snapshots are immutable verbatim public-repo bytes at the scanned ref (see
`.claude/rules/security.md` § Vendor-data isolation). Diffs are computed
on-demand and CPU-bounded by the per-file line cap + total-bytes cap below;
the router runs the heavy diff under `asyncio.to_thread`.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact_blob import ArtifactBlob
from app.models.scan import Scan

# Bound the work an anonymous caller can trigger.
_MAX_LINES_PER_FILE = 2000  # beyond this, collapse the file to a summary entry
_MAX_TOTAL_DIFF_BYTES = 512 * 1024  # ~512 KiB of diff line text, then truncate

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass
class DiffLine:
    type: str  # "add" | "del" | "ctx"
    text: str
    gutter: str


@dataclass
class DiffHunk:
    header: str
    lines: list[DiffLine] = field(default_factory=list)  # type: ignore[arg-type]


@dataclass
class DiffFile:
    path: str
    status: str  # "added" | "removed" | "modified" | "binary"
    hunks: list[DiffHunk] = field(default_factory=list)  # type: ignore[arg-type]
    note: str | None = None  # set for binary / collapsed entries (no line body)


@dataclass
class DiffResult:
    files: list[DiffFile]
    truncated: bool = False


async def load_snapshot(session: AsyncSession, scan: Scan) -> dict[str, bytes | None]:
    """Resolve `scans.file_hashes` → `{path: bytes|None}` for one scan.

    `None` = the file is known-but-not-stored (binary / oversize sentinel in the
    map). A missing blob (referenced sha absent) also resolves to `None`.
    """
    file_hashes: dict[str, str | None] = scan.file_hashes or {}
    shas = {sha for sha in file_hashes.values() if sha}
    blobs: dict[str, bytes] = {}
    if shas:
        rows = (
            await session.execute(
                select(ArtifactBlob.sha256, ArtifactBlob.content).where(
                    ArtifactBlob.sha256.in_(shas)
                )
            )
        ).all()
        blobs = {sha: bytes(content) for sha, content in rows}
    return {path: (blobs.get(sha) if sha else None) for path, sha in file_hashes.items()}


def _decode(content: bytes) -> list[str]:
    """UTF-8 (lossy) decode → keepends line list for difflib."""
    return content.decode("utf-8", errors="replace").splitlines(keepends=True)


def _unified_to_hunks(old_lines: list[str], new_lines: list[str]) -> list[DiffHunk]:
    """Run `difflib.unified_diff` and parse it into structured hunks with gutters.

    Gutter shows the new-file line number for context/added lines and the
    old-file line number for deletions — the usual unified-diff reading.
    """
    hunks: list[DiffHunk] = []
    current: DiffHunk | None = None
    old_ln = new_ln = 0

    for raw in difflib.unified_diff(old_lines, new_lines, lineterm=""):
        if raw.startswith("---") or raw.startswith("+++"):
            continue
        if raw.startswith("@@"):
            m = _HUNK_RE.match(raw)
            old_ln = int(m.group(1)) if m else 0
            new_ln = int(m.group(2)) if m else 0
            current = DiffHunk(header=raw)
            hunks.append(current)
            continue
        if current is None:  # defensive: body line before any hunk header
            continue
        sign, text = raw[:1], raw[1:].rstrip("\n")
        if sign == "+":
            current.lines.append(DiffLine(type="add", text=text, gutter=str(new_ln)))
            new_ln += 1
        elif sign == "-":
            current.lines.append(DiffLine(type="del", text=text, gutter=str(old_ln)))
            old_ln += 1
        else:  # context line
            current.lines.append(DiffLine(type="ctx", text=text, gutter=str(new_ln)))
            old_ln += 1
            new_ln += 1
    return hunks


def diff_snapshots(old: Mapping[str, bytes | None], new: Mapping[str, bytes | None]) -> DiffResult:
    """Diff two `{path: bytes|None}` snapshots into structured per-file hunks.

    Identical files are skipped. Binary / not-stored files (None) are emitted as
    flagged entries with no line body. Per-file line cap collapses huge diffs to
    a summary; a total-bytes cap sets `truncated` and stops emitting further
    files.
    """
    files: list[DiffFile] = []
    truncated = False
    total_bytes = 0

    for path in sorted(set(old) | set(new)):
        if total_bytes >= _MAX_TOTAL_DIFF_BYTES:
            truncated = True
            break

        in_old, in_new = path in old, path in new
        o, n = old.get(path), new.get(path)

        # Binary / not-stored on either side — can't line-diff.
        if (in_old and o is None) or (in_new and n is None):
            if in_old and in_new and o is None and n is None:
                continue  # binary present in both, unchanged as far as we know
            files.append(
                DiffFile(
                    path=path,
                    status="binary",
                    note="binary or oversize file — content not stored",
                )
            )
            continue

        old_lines = _decode(o) if o is not None else []
        new_lines = _decode(n) if n is not None else []
        if old_lines == new_lines:
            continue  # unchanged

        if not in_old:
            status = "added"
        elif not in_new:
            status = "removed"
        else:
            status = "modified"

        line_count = len(old_lines) + len(new_lines)
        if line_count > _MAX_LINES_PER_FILE:
            files.append(
                DiffFile(
                    path=path,
                    status=status,
                    note=f"large change ({line_count} lines) — diff collapsed",
                )
            )
            continue

        hunks = _unified_to_hunks(old_lines, new_lines)
        for h in hunks:
            total_bytes += sum(len(line.text) for line in h.lines)
        files.append(DiffFile(path=path, status=status, hunks=hunks))

    return DiffResult(files=files, truncated=truncated)
