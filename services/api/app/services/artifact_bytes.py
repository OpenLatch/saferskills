"""Storage-split snapshot byte resolver (I-3.5, D-UP-12).

A scan's `file_hashes` maps `{path -> sha256 | null}`. The bytes live in one of
two stores depending on the run's source x visibility:

- `artifact_blobs` — content-addressed, deduped, indefinite. Public scans
  (github/any + upload/public) capture here.
- `upload_files` — per-run, NO dedup, 90-day transient. Unlisted uploads capture
  here (per-run isolation avoids dedup-induced privacy coupling).

This resolver hides the split so the diff / render / `.zip` code stays uniform:
it tries `artifact_blobs` by sha first, then falls back to `upload_files` by
`(scan_run_id, path)`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact_blob import ArtifactBlob
from app.models.scan import Scan
from app.models.upload_file import UploadFile


async def resolve_snapshot(session: AsyncSession, scan: Scan) -> dict[str, bytes | None]:
    """Resolve a scan's whole snapshot → `{path: bytes|None}` in ≤2 queries.

    `None` = known-but-not-stored (binary / oversize sentinel) or a missing blob.
    `artifact_blobs` is consulted by sha; any path not satisfied there (and any
    null-sha path) is looked up in `upload_files` by `(scan_run_id, path)`.
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

    # Anything not resolved from blobs (null sha or absent blob) may live in the
    # per-run upload store — fetch the run's upload_files once and map by path.
    needs_upload = any(not sha or sha not in blobs for sha in file_hashes.values())
    upload_map: dict[str, bytes | None] = {}
    if needs_upload and scan.scan_run_id is not None:
        rows = (
            await session.execute(
                select(UploadFile.path, UploadFile.content).where(
                    UploadFile.scan_run_id == scan.scan_run_id
                )
            )
        ).all()
        upload_map = {
            path: (bytes(content) if content is not None else None) for path, content in rows
        }

    out: dict[str, bytes | None] = {}
    for path, sha in file_hashes.items():
        if sha and sha in blobs:
            out[path] = blobs[sha]
        elif path in upload_map:
            out[path] = upload_map[path]
        else:
            out[path] = None
    return out


async def resolve(session: AsyncSession, scan: Scan, path: str, sha: str | None) -> bytes | None:
    """Resolve a single `(path, sha)` to its bytes — `artifact_blobs` first
    (by sha), else `upload_files` (by `scan_run_id` + path). Returns None when
    neither store holds it (binary/oversize sentinel or missing)."""
    if sha:
        blob = (
            await session.execute(select(ArtifactBlob.content).where(ArtifactBlob.sha256 == sha))
        ).scalar_one_or_none()
        if blob is not None:
            return bytes(blob)
    if scan.scan_run_id is not None:
        content = (
            await session.execute(
                select(UploadFile.content)
                .where(UploadFile.scan_run_id == scan.scan_run_id, UploadFile.path == path)
                .limit(1)
            )
        ).scalar_one_or_none()
        if content is not None:
            return bytes(content)
    return None
