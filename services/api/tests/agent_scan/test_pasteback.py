"""Paste-back decode (I-5.5, D-5.5-17). Round-trip + the ratio/size guards."""

from __future__ import annotations

import base64
import gzip
import hashlib

import pytest

from app.agent_scan.pasteback import PASTEBACK_MAX_PASTED_BYTES, decode_pasteback
from app.scan.upload import UploadRejected

_JSON = b'{"schema_version":"agent_scan_result.v1","tests":[]}'


def _blob(raw: bytes) -> str:
    return base64.urlsafe_b64encode(gzip.compress(raw)).decode().rstrip("=")


def test_bare_blob_round_trip() -> None:
    assert decode_pasteback(_blob(_JSON)) == _JSON


def test_fenced_header_round_trip() -> None:
    body = _blob(_JSON)
    text = (
        f"SAFERSKILLS-AGENTSCAN-v1 sha256={hashlib.sha256(_JSON).hexdigest()[:16]} len={len(_JSON)}\n"
        f"```\n{body}\n```\n"
    )
    assert decode_pasteback(text) == _JSON


def test_header_sha_mismatch_rejected() -> None:
    body = _blob(_JSON)
    text = f"SAFERSKILLS-AGENTSCAN-v1 sha256={'0' * 16} len={len(_JSON)}\n{body}"
    with pytest.raises(UploadRejected) as exc:
        decode_pasteback(text)
    assert exc.value.status == 422


def test_ratio_bomb_rejected() -> None:
    # 5 MiB of zeros gzips tiny -> ratio > 100 -> archive_rejected/ratio.
    bomb = _blob(b"\x00" * (5 * 1024 * 1024))
    with pytest.raises(UploadRejected) as exc:
        decode_pasteback(bomb)
    assert exc.value.reason in {"ratio", "too_big"}


def test_oversize_pasted_rejected() -> None:
    with pytest.raises(UploadRejected) as exc:
        decode_pasteback("A" * (PASTEBACK_MAX_PASTED_BYTES + 1))
    assert exc.value.reason == "too_big"


def test_garbage_rejected() -> None:
    with pytest.raises(UploadRejected) as exc:
        decode_pasteback("not base64 !!!! and not gzip")
    assert exc.value.status == 422
