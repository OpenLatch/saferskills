"""Validation + safe extraction for direct artifact uploads (I-3.5).

Turns an uploaded body (one capability file, one `.zip`, or N loose files —
combined ≤10 MiB) into the **same** `list[tuple[str, bytes]]` file index
`app/scan/fetch.py::walk_files` produces, so everything downstream
(`discover_capabilities` → per-capability scoring → trace → persistence) is
unchanged and source-agnostic. The engine never knows the source.

Security posture (see `.claude/rules/security.md` § Public-input handling):
- cumulative size cap enforced in the multipart parser (the body never lands
  whole before the cap can fire) — across ALL parts combined;
- extension allowlist + magic-byte sniff (spoofed Content-Type caught);
- `.zip` extraction enforces the full bomb / Zip-Slip / nesting / path-length /
  NFC / duplicate-fold cap set incrementally, aborting on the first breach;
- a multi-file batch forbids archives (`nesting`), sanitizes each part path with
  the shared `_safe_relpath` (`zip_slip`/`bad_path`), and dedups by casefold
  (`dup_path`) — reusing the already-audited zip containment;
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


def _safe_single_name(filename: str) -> str:
    """Basename of a single uploaded file, NFC-normalized, fallback `artifact`."""
    name = unicodedata.normalize("NFC", Path(filename).name).strip()
    return name or "artifact"


def _batch_original_filename(parts: list[tuple[str, bytes]]) -> str:
    """Display-only label for a multi-file batch. The durable identity is the
    `content_hash` over `files_index`, so this never feeds the idempotency cache."""
    n = len(parts)
    return f"{n} file{'s' if n != 1 else ''}"


def _safe_relpath(filename: str, real_tmp: str) -> str | None:
    """Sanitize an archive entry / loose part name into a safe relative POSIX
    path. Shared by `_extract_zip` and `_extract_loose_batch` — the same audited
    containment surface (no new attack surface).

    NFC-normalizes, then rejects absolute / `..` / tempdir-escaping paths
    (`zip_slip`) and over-length paths (`bad_path`). Returns `None` to DROP a
    top-level `.git/` entry (VCS noise, never capability content)."""
    name = unicodedata.normalize("NFC", filename)
    posix = name.replace("\\", "/")
    parts = PurePosixPath(posix).parts

    # Containment: absolute, `..`, or escaping the tempdir → Zip-Slip.
    dest = os.path.realpath(os.path.join(real_tmp, posix))
    escapes = not (dest == real_tmp or dest.startswith(real_tmp + os.sep))
    if posix.startswith("/") or ".." in parts or escapes:
        raise UploadRejected(422, "archive_rejected", "zip_slip")

    if len(posix) > _PATH_MAX:
        raise UploadRejected(422, "archive_rejected", "bad_path")

    # Dotfile policy: keep committed dotfiles (.env etc.), but drop VCS internals
    # under a top-level .git/ (noise, never capability content).
    if parts and parts[0] == ".git":
        return None
    return posix


def extract_upload(parts: list[tuple[str, bytes]], *, settings: Settings) -> ExtractedUpload:
    """Validate + extract uploaded file part(s) into an engine-ready file index.

    One part → the single-file / single-`.zip` path (byte-for-byte unchanged).
    N parts → the loose-batch path (scanned like a repo subtree). The cumulative
    size cap is enforced upstream in the multipart parser; here we only validate
    type + containment per part."""
    if not parts:
        raise UploadRejected(422, "malformed_multipart")

    if len(parts) == 1:
        filename, body = parts[0]
        files_index = _extract_single_body(filename, body, settings)
        original_filename = _safe_single_name(filename)
        detect_filename = filename
    else:
        files_index = _extract_loose_batch(parts, settings)
        original_filename = _batch_original_filename(parts)
        detect_filename = files_index[0][0] if files_index else "artifact"

    detected_kind, detected_name = _detect(files_index, detect_filename)
    return ExtractedUpload(
        files_index=files_index,
        original_filename=original_filename,
        detected_kind=detected_kind,
        detected_name=detected_name,
    )


def _extract_single_body(filename: str, body: bytes, settings: Settings) -> list[tuple[str, bytes]]:
    """The original single-file / single-`.zip` logic, factored out unchanged:
    a `.zip` extracts with the full safety-cap set; any other allowed extension
    is one text file (binaries rejected)."""
    ext = _ext(filename)
    if ext not in settings.upload_allowed_extensions:
        raise UploadRejected(415, "unsupported_type")
    if ext == ".zip":
        return _extract_zip(body, settings)
    if _looks_binary(body):
        raise UploadRejected(415, "binary_not_allowed")
    return [(_safe_single_name(filename), body)]


def _extract_loose_batch(
    parts: list[tuple[str, bytes]], settings: Settings
) -> list[tuple[str, bytes]]:
    """Extract N loose file parts into a structured file index — "scan it like a
    repo". Per part: forbid archives (`nesting`, mirroring no-archive-in-archive),
    enforce the extension allowlist + binary sniff, sanitize the path via the
    shared `_safe_relpath`, and reject casefold-duplicates (`dup_path`). Relative
    paths are preserved so `skill/SKILL.md` + `skill/script.py` discover as one
    subtree."""
    files_index: list[tuple[str, bytes]] = []
    seen_folded: set[str] = set()

    # The tempdir is the canonical containment base for the Zip-Slip check (same
    # as `_extract_zip`); we never write bytes to it.
    with tempfile.TemporaryDirectory() as tmp:
        real_tmp = os.path.realpath(tmp)
        for filename, body in parts:
            ext = _ext(filename)
            if filename.lower().endswith(_NESTED_ARCHIVE_SUFFIXES):
                raise UploadRejected(422, "archive_rejected", "nesting")
            if ext not in settings.upload_allowed_extensions:
                raise UploadRejected(415, "unsupported_type")
            if _looks_binary(body):
                raise UploadRejected(415, "binary_not_allowed")

            posix = _safe_relpath(filename, real_tmp)
            if posix is None:
                continue  # top-level .git/ — dropped

            folded = posix.casefold()
            if folded in seen_folded:
                raise UploadRejected(422, "archive_rejected", "dup_path")
            seen_folded.add(folded)
            files_index.append((posix, body))

    if not files_index:
        raise UploadRejected(422, "malformed_multipart")
    return files_index


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

            # Symlink entries (defeats containment) → reject.
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise UploadRejected(422, "archive_rejected", "zip_slip")

            if info.filename.replace("\\", "/").lower().endswith(_NESTED_ARCHIVE_SUFFIXES):
                raise UploadRejected(422, "archive_rejected", "nesting")

            # Shared containment + sanitization (NFC, Zip-Slip, path-length, .git).
            posix = _safe_relpath(info.filename, real_tmp)
            if posix is None:
                continue  # top-level .git/ — dropped

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
