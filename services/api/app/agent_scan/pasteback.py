"""Paste-back blob decode (I-5.5, D-5.5-17).

When the agent has no fetch tool it prints its evidence as a `base64url(gzip(
agent_scan_result.v1 JSON))` block, optionally fenced + prefixed by a one-line
header `SAFERSKILLS-AGENTSCAN-v1 sha256=<first16hex> len=<bytes>`. The user pastes
it at the web submit (I-5.7) or `saferskills scan agent --submit-blob`; the submit
endpoint decodes it here.

Bucketed-error contract (reuses `app.scan.upload.UploadRejected` - same
`{"error":...,"reason":...}` envelope the frontend `mapUploadError` parses, no new
error code): pasted > 512 KiB -> `422 archive_rejected/too_big`; decompressed >
`upload_max_bytes` (10 MiB) -> `too_big`; decompressed/compressed ratio > 100 ->
`ratio`; malformed base64/gzip -> `bad_blob`. The decompress is capped + incremental
(`zlib.decompressobj`), so a zip-bomb can never allocate past the cap.
"""

from __future__ import annotations

import base64
import hashlib
import re
import zlib

from app.core.config import get_settings
from app.scan.upload import UploadRejected

# Pasted-text cap (the raw blob a human copies) - distinct from the decoded cap.
PASTEBACK_MAX_PASTED_BYTES = 512 * 1024
# Max decompressed/compressed ratio before we call it a bomb (D-5.5-17).
_MAX_RATIO = 100

_HEADER_RE = re.compile(r"^SAFERSKILLS-AGENTSCAN-v1\s+sha256=([0-9a-fA-F]{16})\s+len=(\d+)\s*$")
_FENCE_RE = re.compile(r"^```.*$")


def _gunzip_capped(blob: bytes, *, max_out: int) -> bytes:
    """Incrementally gunzip `blob`, refusing to allocate past `max_out` bytes."""
    decompressor = zlib.decompressobj(wbits=31)  # 31 = gzip header/trailer
    try:
        out = decompressor.decompress(blob, max_out + 1)
        if decompressor.unconsumed_tail:
            raise UploadRejected(422, "archive_rejected", "too_big")
        out += decompressor.flush()
    except zlib.error as exc:
        raise UploadRejected(422, "archive_rejected", "bad_blob") from exc
    if len(out) > max_out:
        raise UploadRejected(422, "archive_rejected", "too_big")
    if blob and len(out) / len(blob) > _MAX_RATIO:
        raise UploadRejected(422, "archive_rejected", "ratio")
    return out


def decode_pasteback(text: str) -> bytes:
    """Decode a paste-back blob (fenced/header form OR a bare base64url token) to
    the raw `agent_scan_result.v1` JSON bytes. Raises `UploadRejected` on any cap
    or integrity failure.

    A bare base64url string (the JSON `paste_back` field) has no header/fence and
    flows through the same path - the header verification is simply skipped.
    """
    if len(text.encode("utf-8")) > PASTEBACK_MAX_PASTED_BYTES:
        raise UploadRejected(422, "archive_rejected", "too_big")

    declared_sha16: str | None = None
    declared_len: int | None = None
    token_parts: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or _FENCE_RE.match(stripped):
            continue
        header = _HEADER_RE.match(stripped)
        if header is not None:
            declared_sha16, declared_len = header.group(1).lower(), int(header.group(2))
            continue
        token_parts.append(stripped)

    token = "".join(token_parts)
    if not token:
        raise UploadRejected(422, "archive_rejected", "bad_blob")

    # urlsafe_b64decode is strict about padding; restore it from the length.
    padded = token + "=" * (-len(token) % 4)
    try:
        blob = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise UploadRejected(422, "archive_rejected", "bad_blob") from exc

    raw = _gunzip_capped(blob, max_out=get_settings().upload_max_bytes)

    if declared_sha16 is not None:
        if hashlib.sha256(raw).hexdigest()[:16] != declared_sha16:
            raise UploadRejected(422, "archive_rejected", "bad_blob")
        if declared_len is not None and declared_len != len(raw):
            raise UploadRejected(422, "archive_rejected", "bad_blob")
    return raw
