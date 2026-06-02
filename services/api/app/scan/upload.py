"""Validation + safe extraction for direct artifact uploads (I-3.5).

Turns an uploaded body (a single capability file or a `.zip`) into the **same**
`list[tuple[str, bytes]]` file index `app/scan/fetch.py::walk_files` produces, so
everything downstream (`discover_capabilities` → per-capability scoring → trace →
persistence) is unchanged and source-agnostic. The engine never knows the source.

Security posture (see `.claude/rules/security.md` § Public-input handling):
- streaming size cap (the body never lands whole before the cap can fire);
- extension allowlist + magic-byte sniff (spoofed Content-Type caught);
- `.zip` extraction enforces the full bomb / Zip-Slip / nesting / path-length /
  NFC / duplicate-fold cap set incrementally, aborting on the first breach;
- bytes are read as data only — never imported, eval'd, or shelled.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import secrets
import tempfile
import unicodedata
import zipfile
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, cast

from app.scan.persistence import _looks_binary  # pyright: ignore[reportPrivateUsage]

if TYPE_CHECKING:
    from app.core.config import Settings

# Magic bytes for a local-file-header zip and an empty-archive end-of-central-dir.
_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06")
# Nested-archive extensions rejected at depth 0 (no archive-in-archive).
_NESTED_ARCHIVE_SUFFIXES = (".zip", ".gz", ".tar", ".tgz", ".7z", ".rar")
_READ_CHUNK = 64 * 1024
_PATH_MAX = 1024  # matches upload_files.path VARCHAR(1024) + findings path cap


class UploadRejected(Exception):
    """An upload failed validation — carries the HTTP mapping triple.

    `status` is the HTTP status, `code` the stable machine error code, `reason`
    the bucketed sub-reason for `422 archive_rejected` (else None).
    """

    def __init__(self, status: int, code: str, reason: str | None = None) -> None:
        super().__init__(f"{code}:{reason}" if reason else code)
        self.status = status
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class ExtractedUpload:
    files_index: list[tuple[str, bytes]]  # (relative_path, bytes) — engine-ready
    original_filename: str
    detected_kind: str | None
    detected_name: str | None


def _ext(filename: str) -> str:
    return Path(filename).suffix.lower()


async def _read_capped(stream: AsyncIterator[bytes], max_bytes: int) -> bytes:
    """Drain an async byte stream, aborting the moment the cap is exceeded.

    Belt-and-suspenders: the multipart handler already tallies + aborts at the
    same cap (`app/routers/scans.py`), so this rarely fires — but it keeps
    `extract_upload` safe for any caller (e.g. the CLI in I-05).
    """
    buf = bytearray()
    async for chunk in stream:
        buf += chunk
        if len(buf) > max_bytes:
            raise UploadRejected(413, "upload_too_large")
    return bytes(buf)


def _safe_single_name(filename: str) -> str:
    """Basename of a single uploaded file, NFC-normalized, fallback `artifact`."""
    name = unicodedata.normalize("NFC", Path(filename).name).strip()
    return name or "artifact"


async def extract_upload(
    stream: AsyncIterator[bytes], filename: str, *, settings: Settings
) -> ExtractedUpload:
    """Validate + extract an uploaded body into an engine-ready file index."""
    body = await _read_capped(stream, settings.upload_max_bytes)
    ext = _ext(filename)
    if ext not in settings.upload_allowed_extensions:
        raise UploadRejected(415, "unsupported_type")

    if ext == ".zip":
        files_index = _extract_zip(body, settings)
    else:
        if _looks_binary(body):
            raise UploadRejected(415, "binary_not_allowed")
        files_index = [(_safe_single_name(filename), body)]

    detected_kind, detected_name = _detect(files_index, filename)
    return ExtractedUpload(
        files_index=files_index,
        original_filename=_safe_single_name(filename),
        detected_kind=detected_kind,
        detected_name=detected_name,
    )


def _extract_zip(body: bytes, settings: Settings) -> list[tuple[str, bytes]]:
    """Extract a `.zip` body into a file index, enforcing every safety cap.

    `zipfile` does no size validation (CVE-2019-9674) and 28M:1 overlap bombs
    exist — so each member is read decompressed in bounded chunks (never trusting
    `ZipInfo.file_size`), with per-file / total / ratio / entry-count guards
    applied incrementally, plus Zip-Slip canonicalization, nesting-depth-0,
    path-length, NFC normalization, and duplicate-after-fold rejection.
    """
    if body[:4] not in _ZIP_MAGIC:
        raise UploadRejected(415, "unsupported_type")
    try:
        zf = zipfile.ZipFile(io.BytesIO(body))
    except zipfile.BadZipFile as exc:
        raise UploadRejected(415, "unsupported_type") from exc

    files_index: list[tuple[str, bytes]] = []
    total = 0
    entry_count = 0
    seen_folded: set[str] = set()

    # The tempdir is the canonical containment base for Zip-Slip checks. We never
    # write member bytes to disk (read-into-memory only), so it stays empty.
    with tempfile.TemporaryDirectory() as tmp:
        real_tmp = os.path.realpath(tmp)
        for info in zf.infolist():
            if info.is_dir():
                continue

            name = unicodedata.normalize("NFC", info.filename)

            # Symlink entries (defeats containment) → reject.
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise UploadRejected(422, "archive_rejected", "zip_slip")

            posix = name.replace("\\", "/")
            lower = posix.lower()
            if lower.endswith(_NESTED_ARCHIVE_SUFFIXES):
                raise UploadRejected(422, "archive_rejected", "nesting")

            # Containment: absolute, `..`, or escaping the tempdir → Zip-Slip.
            parts = PurePosixPath(posix).parts
            dest = os.path.realpath(os.path.join(real_tmp, posix))
            escapes = not (dest == real_tmp or dest.startswith(real_tmp + os.sep))
            if posix.startswith("/") or ".." in parts or escapes:
                raise UploadRejected(422, "archive_rejected", "zip_slip")

            if len(posix) > _PATH_MAX:
                raise UploadRejected(422, "archive_rejected", "bad_path")

            # Dotfile policy: keep committed dotfiles (.env etc.), but drop VCS
            # internals under a top-level .git/ (noise, never capability content).
            if parts and parts[0] == ".git":
                continue

            folded = posix.casefold()
            if folded in seen_folded:
                raise UploadRejected(422, "archive_rejected", "dup_path")
            seen_folded.add(folded)

            entry_count += 1
            if entry_count > settings.upload_extract_max_entries:
                raise UploadRejected(422, "archive_rejected", "entries")

            # Read decompressed bytes in bounded chunks — the only honest size cap.
            read = 0
            chunks: list[bytes] = []
            with zf.open(info) as member:
                while True:
                    chunk = member.read(_READ_CHUNK)
                    if not chunk:
                        break
                    read += len(chunk)
                    if read > settings.upload_extract_max_per_file_bytes:
                        raise UploadRejected(422, "archive_rejected", "too_big")
                    total += len(chunk)
                    if total > settings.upload_extract_max_total_bytes:
                        raise UploadRejected(422, "archive_rejected", "too_big")
                    chunks.append(chunk)

            # Incremental compression ratio. A zero compressed size with a body is
            # an infinite ratio (don't divide by zero); a fully-empty entry is fine.
            comp = info.compress_size
            if comp == 0:
                if read > 0:
                    raise UploadRejected(422, "archive_rejected", "ratio")
            elif read / comp > settings.upload_extract_max_ratio:
                raise UploadRejected(422, "archive_rejected", "ratio")

            files_index.append((posix, b"".join(chunks)))

    return files_index


# ── Kind + name detection (D-UP-10) ──────────────────────────────────────────


def _detect(files_index: list[tuple[str, bytes]], filename: str) -> tuple[str | None, str | None]:
    """Detected (kind, name) for the run. Kind = the primary capability's kind
    (discovery's lone-markdown → skill fallback already applies); name resolves
    declared-name → filename stem → 'artifact'."""
    from app.scan.discovery import discover_capabilities

    detected_kind: str | None = None
    try:
        caps = discover_capabilities(files_index)
        if caps:
            detected_kind = caps[0].kind
    except Exception:
        detected_kind = None

    return detected_kind, _detect_name(files_index, filename)


def _frontmatter_name(content: bytes) -> str | None:
    """`name:` from a leading `---` YAML frontmatter block (no yaml dep)."""
    text = content[:8192].decode("utf-8", errors="replace")
    if not text.lstrip().startswith("---"):
        return None
    body = text.split("---", 2)
    if len(body) < 3:
        return None
    for line in body[1].splitlines():
        m = re.match(r"\s*name\s*:\s*(.+?)\s*$", line)
        if m:
            return m.group(1).strip().strip("'\"") or None
    return None


def _json_name(content: bytes) -> str | None:
    try:
        raw = json.loads(content[:65536].decode("utf-8", errors="replace"))
    except ValueError, UnicodeDecodeError:
        return None
    if isinstance(raw, dict):
        name = cast("dict[str, object]", raw).get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def _detect_name(files_index: list[tuple[str, bytes]], filename: str) -> str | None:
    by_base: dict[str, bytes] = {}
    for path, content in files_index:
        by_base.setdefault(path.rsplit("/", 1)[-1].lower(), content)

    if "skill.md" in by_base:
        name = _frontmatter_name(by_base["skill.md"])
        if name:
            return name
    for manifest in ("mcp.json", ".mcp.json", "plugin.json", "manifest.json"):
        if manifest in by_base:
            name = _json_name(by_base[manifest])
            if name:
                return name

    stem = Path(filename).stem.strip()
    return stem or "artifact"


# ── Identity + idempotency (D-UP-11, D-UP-28) ────────────────────────────────


def upload_content_hash(files_index: list[tuple[str, bytes]]) -> str:
    """sha256 of the sorted `{path: sha256(bytes)}` map — the durable artifact
    identity (mirrors `persistence._snapshot_identity` semantics)."""
    file_map = {path: hashlib.sha256(content).hexdigest() for path, content in files_index}
    canonical = json.dumps(file_map, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def public_upload_idempotency_key(content_hash: str, rubric_version: str) -> str:
    """PUBLIC uploads cache like today — same bytes + rubric → the existing run."""
    raw = f"{content_hash}|{rubric_version}|public"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def unlisted_idempotency_key(content_hash: str, rubric_version: str) -> str:
    """UNLISTED uploads NEVER cache — a per-submission nonce makes two byte-
    identical private submissions distinct runs + distinct tokens (D-UP-28),
    killing cross-user privacy coupling."""
    raw = f"{content_hash}|{rubric_version}|unlisted|{secrets.token_hex(16)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
