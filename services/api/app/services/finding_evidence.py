"""Per-finding evidence-excerpt resolution (report-DTO-only).

For each finding, resolve the matched-line window from the **stored snapshot**
(`artifact_blobs` / `upload_files`, via `artifact_bytes.resolve_snapshot`) so the
report can render the exact value that was spotted, with a line gutter and the
hit line highlighted (the v3 `.find-card` `.ex` block).

This is deliberately NOT a scan-trace field and is NEVER persisted on the
`findings` table — the trace stays hash-only per `.claude/rules/security.md`
§ Scan-trace transparency. The bytes here come from the already-public stored
snapshot (or the token-gated unlisted store), carried only on the report
response. Verbatim bytes are returned (invisible/bidi chars preserved — the
frontend reveals them); the resolver only bounds the window + line length.

Graceful degradation: a file that is absent from the snapshot (binary / oversize
sentinel / expired) yields NO excerpt for its findings — the frontend then shows
a "value not stored" affordance rather than breaking.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog_item import CatalogItem
from app.models.scan import Finding, Scan
from app.services.artifact_bytes import resolve_snapshot


class EvidenceLineDict(TypedDict):
    """One line of the matched-line window (mirrors the wire `evidence_excerpt`)."""

    line_no: int
    text: str
    hit: bool


class EvidenceExcerptDict(TypedDict):
    """Report-DTO-only matched-line window resolved from the stored snapshot."""

    file: str
    lang: str | None
    truncated: bool
    lines: list[EvidenceLineDict]


# Window budget — keep each excerpt small + bounded (the wire stays lean).
_CONTEXT_LINES = 2  # lines of context to show each side of the match
_MAX_WINDOW_LINES = 9  # hard ceiling on lines in one excerpt
_MAX_LINE_CHARS = 200  # per-line char cap (the frontend further elides for display)

# Extension → display language hint for the `.ex-meta` "· <lang>" label.
_LANG_BY_EXT: dict[str, str] = {
    "md": "markdown",
    "markdown": "markdown",
    "py": "python",
    "js": "javascript",
    "mjs": "javascript",
    "cjs": "javascript",
    "jsx": "javascript",
    "ts": "typescript",
    "tsx": "typescript",
    "sh": "bash",
    "bash": "bash",
    "zsh": "bash",
    "ps1": "powershell",
    "json": "json",
    "jsonc": "json",
    "yaml": "yaml",
    "yml": "yaml",
    "toml": "toml",
    "mdc": "markdown",
    "txt": "text",
    "env": "bash",
}


def _lang_for(path: str) -> str | None:
    """Best-effort language hint from the file extension (display only)."""
    base = path.rsplit("/", 1)[-1]
    if "." not in base:
        return None
    ext = base.rsplit(".", 1)[-1].lower()
    return _LANG_BY_EXT.get(ext)


def _excerpt_for(content: bytes, finding: Finding) -> EvidenceExcerptDict | None:
    """Build the bounded matched-line window for one finding, or None.

    None when the recorded line range cannot be located in the (possibly drifted)
    snapshot — the frontend then falls back to "value not stored".
    """
    text = content.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if not lines:
        return None

    start = finding.line_start
    if start < 1 or start > len(lines):
        return None
    end = finding.line_end or start
    end = min(max(end, start), len(lines))

    truncated = False
    # Clamp the hit span itself to the window budget (huge multi-line matches).
    if end - start + 1 > _MAX_WINDOW_LINES:
        end = start + _MAX_WINDOW_LINES - 1
        truncated = True

    span = end - start + 1
    # Distribute any remaining line budget as symmetric context.
    ctx = min(_CONTEXT_LINES, max(0, (_MAX_WINDOW_LINES - span) // 2))
    win_start = max(1, start - ctx)
    win_end = min(len(lines), end + ctx)

    out_lines: list[EvidenceLineDict] = []
    for line_no in range(win_start, win_end + 1):
        raw = lines[line_no - 1]
        if len(raw) > _MAX_LINE_CHARS:
            raw = raw[:_MAX_LINE_CHARS]
            truncated = True
        out_lines.append({"line_no": line_no, "text": raw, "hit": start <= line_no <= end})

    return {
        "file": finding.file_path,
        "lang": _lang_for(finding.file_path),
        "truncated": truncated,
        "lines": out_lines,
    }


async def resolve_finding_excerpts(
    session: AsyncSession, scan: Scan, findings: Sequence[Finding]
) -> dict[str, EvidenceExcerptDict]:
    """Resolve `{finding_id -> excerpt}` for one scan's findings.

    Calls `resolve_snapshot` once for the scan, then slices the matched-line
    window out of each needed file. Findings whose file is absent from the
    snapshot are simply omitted (no excerpt key) — graceful fallback on the
    frontend.
    """
    if not findings:
        return {}
    snapshot = await resolve_snapshot(session, scan)
    out: dict[str, EvidenceExcerptDict] = {}
    for finding in findings:
        content = snapshot.get(finding.file_path)
        if content is None:
            continue
        excerpt = _excerpt_for(content, finding)
        if excerpt is not None:
            out[str(finding.id)] = excerpt
    return out


async def resolve_run_evidence(
    session: AsyncSession,
    capabilities: Sequence[tuple[Scan, CatalogItem, Sequence[Finding]]],
) -> dict[str, EvidenceExcerptDict]:
    """Resolve excerpts across every capability of a repo scan run.

    Each capability's scan has its own per-subtree `file_hashes`, so the snapshot
    is resolved per scan. Finding ids are globally unique, so the merged map is a
    flat `{finding_id -> excerpt}`.
    """
    out: dict[str, EvidenceExcerptDict] = {}
    for scan, _item, findings in capabilities:
        out.update(await resolve_finding_excerpts(session, scan, findings))
    return out
