"""Tests for app.ingestion.framework.content_hash.compute_artifact_hash."""

from __future__ import annotations

import hashlib

from app.ingestion.framework.content_hash import compute_artifact_hash


class TestComputeArtifactHash:
    def test_deterministic_same_input(self) -> None:
        files = {"SKILL.md": b"hello world", "mcp.json": b'{"transport":"stdio"}'}
        h1 = compute_artifact_hash(files)
        h2 = compute_artifact_hash(files)
        assert h1 == h2

    def test_order_invariant(self) -> None:
        """The hash must be the same regardless of key insertion order."""
        files_a = {"SKILL.md": b"hello", "README.md": b"world"}
        files_b = {"README.md": b"world", "SKILL.md": b"hello"}
        assert compute_artifact_hash(files_a) == compute_artifact_hash(files_b)

    def test_empty_dict_returns_sha256_of_empty(self) -> None:
        expected = hashlib.sha256(b"").hexdigest()
        assert compute_artifact_hash({}) == expected

    def test_none_returns_sha256_of_empty(self) -> None:
        expected = hashlib.sha256(b"").hexdigest()
        assert compute_artifact_hash(None) == expected

    def test_different_content_produces_different_hash(self) -> None:
        h1 = compute_artifact_hash({"SKILL.md": b"version 1"})
        h2 = compute_artifact_hash({"SKILL.md": b"version 2"})
        assert h1 != h2

    def test_different_keys_produce_different_hash(self) -> None:
        h1 = compute_artifact_hash({"SKILL.md": b"data"})
        h2 = compute_artifact_hash({"mcp.json": b"data"})
        assert h1 != h2

    def test_returns_64_char_hex(self) -> None:
        result = compute_artifact_hash({"file.txt": b"x"})
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_content_hash_is_over_file_hashes_not_bytes(self) -> None:
        """The artifact hash is built from per-file SHA-256 digests, not raw bytes.

        Two different files with different content must hash differently,
        but the structure ensures reproducibility via JCS canonicalisation.
        """
        files = {"a.txt": b"aaa", "b.txt": b"bbb"}
        result = compute_artifact_hash(files)
        assert isinstance(result, str)
        # Verify it is NOT simply sha256 of all bytes concatenated
        raw_concat = b"aaa" + b"bbb"
        assert result != hashlib.sha256(raw_concat).hexdigest()

    def test_single_file(self) -> None:
        result = compute_artifact_hash({"only.txt": b"content"})
        assert isinstance(result, str)
        assert len(result) == 64
