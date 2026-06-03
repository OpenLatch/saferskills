"""JCS-canonical SHA-256 per RFC 8785 (D-04-16).

The same function OpenLatch Capability Control uses (Two-Motion Strategy lock).
Computed over a stable projection of the artifact manifest (filename → per-file
sha256), so it is invariant to dict ordering and detects rug-pull content drift.
"""

from __future__ import annotations

import hashlib

import rfc8785


def compute_artifact_hash(metadata_files: dict[str, bytes] | None) -> str:
    """Return the 64-char hex SHA-256 of the JCS-canonical manifest projection.

    Input: {filename: bytes} (SKILL.md, mcp.json, package.json, …).
    Stable across key reordering (RFC 8785 canonicalisation).
    """
    if not metadata_files:
        return hashlib.sha256(b"").hexdigest()
    projection = {
        filename: hashlib.sha256(body).hexdigest()
        for filename, body in sorted(metadata_files.items())
    }
    canonical = rfc8785.dumps(projection)
    return hashlib.sha256(canonical).hexdigest()
