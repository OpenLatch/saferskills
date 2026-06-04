"""Shared CLI Proof-of-Work test helpers (D-05-30).

The brute-force solver + leading-zero-bit counter are needed by both the service
test (`tests/services/test_cli_pow.py`) and the gate route test
(`tests/routers/test_cli_pow_gate.py`); they live here so the two never drift.
"""

from __future__ import annotations

import hashlib


def leading_zero_bits(digest: bytes) -> int:
    """Most-significant leading zero bits of a digest (mirrors the verify math)."""
    bits = 0
    for byte in digest:
        if byte == 0:
            bits += 8
            continue
        bits += 8 - byte.bit_length()
        break
    return bits


def solve_pow(challenge: str, difficulty: int) -> str:
    """Brute-force a solution clearing `difficulty` leading zero bits — the same
    `sha256(challenge + solution)` the backend verifies and the CLI solves."""
    n = 0
    while True:
        if leading_zero_bits(hashlib.sha256((challenge + str(n)).encode()).digest()) >= difficulty:
            return str(n)
        n += 1
