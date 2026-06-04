"""Unit tests for the stateless CLI Proof-of-Work gate (D-05-30).

Covers good / forged / expired / replayed / insufficient-difficulty / secret-unset.
The single-use INSERT needs a DB session; the pre-INSERT rejections (forged /
expired / weak) raise before touching it but still receive the test session.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.cli_pow import (
    PowDisabled,
    PowRejected,
    issue_challenge,
    verify_pow,
)
from tests.pow_helpers import leading_zero_bits, solve_pow

_SECRET = "test-pow-secret"
_DIFFICULTY = 8  # low so the test solver is fast


@pytest.fixture(autouse=True)
def _configure(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    monkeypatch.setattr(get_settings(), "saferskills_cli_pow_secret", _SECRET)
    monkeypatch.setattr(get_settings(), "cli_pow_difficulty", _DIFFICULTY)


@pytest.mark.asyncio
async def test_good_pow_verifies(db_session: AsyncSession) -> None:
    challenge, difficulty, _exp = issue_challenge()
    assert difficulty == _DIFFICULTY
    solution = solve_pow(challenge, difficulty)
    # No exception == success.
    await verify_pow(f"{challenge}.{solution}", db_session)


@pytest.mark.asyncio
async def test_replay_is_rejected(db_session: AsyncSession) -> None:
    challenge, difficulty, _exp = issue_challenge()
    solution = solve_pow(challenge, difficulty)
    header = f"{challenge}.{solution}"
    await verify_pow(header, db_session)
    with pytest.raises(PowRejected):
        await verify_pow(header, db_session)


@pytest.mark.asyncio
async def test_forged_signature_is_rejected(db_session: AsyncSession) -> None:
    challenge, difficulty, _exp = issue_challenge()
    solution = solve_pow(challenge, difficulty)
    # Flip the last char of the mac (the segment after the '.').
    payload_b64, mac = challenge.rsplit(".", 1)
    tampered_mac = mac[:-1] + ("0" if mac[-1] != "0" else "1")
    header = f"{payload_b64}.{tampered_mac}.{solution}"
    with pytest.raises(PowRejected):
        await verify_pow(header, db_session)


@pytest.mark.asyncio
async def test_expired_is_rejected(db_session: AsyncSession) -> None:
    # Craft a validly-signed but already-expired challenge, mirroring the exact
    # byte-layout documented in cli_pow (compact, key-sorted JSON; HMAC over the
    # raw payload; urlsafe-b64 of the payload joined to the hex mac by '.').
    payload = json.dumps({"exp": 1, "nonce": "deadbeef" * 4}, separators=(",", ":")).encode()
    mac = hmac.new(_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    challenge = f"{base64.urlsafe_b64encode(payload).decode()}.{mac}"
    solution = solve_pow(challenge, _DIFFICULTY)
    with pytest.raises(PowRejected):
        await verify_pow(f"{challenge}.{solution}", db_session)


@pytest.mark.asyncio
async def test_insufficient_difficulty_is_rejected(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    challenge, _difficulty, _exp = issue_challenge()
    # A trivial solution that almost-certainly clears <24 leading zero bits.
    solution = "0"
    assert leading_zero_bits(hashlib.sha256((challenge + solution).encode()).digest()) < 24
    monkeypatch.setattr(get_settings(), "cli_pow_difficulty", 24)
    with pytest.raises(PowRejected):
        await verify_pow(f"{challenge}.{solution}", db_session)


@pytest.mark.asyncio
async def test_malformed_header_is_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(PowRejected):
        await verify_pow("not-a-valid-header", db_session)
    with pytest.raises(PowRejected):
        await verify_pow(None, db_session)


@pytest.mark.asyncio
async def test_secret_unset_disables(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "saferskills_cli_pow_secret", None)
    with pytest.raises(PowDisabled):
        issue_challenge()
    with pytest.raises(PowDisabled):
        await verify_pow("a.b.c", db_session)
