"""Stateless HMAC-signed Proof-of-Work gate for CLI scan-submit (I-05, D-05-30).

The install CLI cannot solve a Cloudflare Turnstile CAPTCHA, so a stateless PoW
challenge replaces Turnstile on the CLI scan-submit path. The server issues a
signed challenge; the CLI brute-forces a `solution` whose hash clears a
difficulty bar; the server re-verifies the signature + the hash + single-use,
WITHOUT having stored the challenge (only solved challenges are persisted, to
block replay).

═══════════════════════════════════════════════════════════════════════════════
EXACT WIRE BYTE-LAYOUT — the CLI (`cli/src/core/pow.rs`) MUST match bit-for-bit.
═══════════════════════════════════════════════════════════════════════════════

1. payload  = the UTF-8 bytes of `json.dumps({"exp": <int>, "nonce": <hex>},
              separators=(",", ":"), sort_keys=True)` — a compact, key-sorted
              JSON object. `exp` is a Unix timestamp (seconds); `nonce` is 32 hex
              chars (16 random bytes).
2. mac      = hex(HMAC_SHA256(key=cli_pow_secret_utf8, msg=payload))  (64 chars)
3. payload_b64 = base64.urlsafe_b64encode(payload).decode("ascii")  (incl. '=' pad)
4. challenge = f"{payload_b64}.{mac}"            ← the opaque string handed to the CLI
5. The CLI finds a `solution` (an ASCII string with NO '.') such that
       sha256( (challenge + solution).encode("ascii") )
   has >= `difficulty` leading ZERO BITS (most-significant-bit-first).
6. The CLI returns the header value:  f"{challenge}.{solution}"
       → three '.'-separated fields total: payload_b64 . mac . solution
       (payload_b64 has no '.'; mac is hex; solution has no '.')

VERIFY (this module): rsplit('.', 1) → (challenge, solution); challenge.rsplit('.',1)
→ (payload_b64, mac). Recompute mac over the decoded payload, constant-time-compare;
check exp not passed; check leading-zero-bits(sha256(challenge+solution)) >= difficulty;
INSERT sha256(challenge) once (replay → reject).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.cli_pow_spent import CliPowSpent

logger = logging.getLogger(__name__)

# Challenge validity window. Long enough for a CLI to solve even a difficulty-28
# challenge on a slow machine, short enough that the single-use ledger stays small.
CHALLENGE_TTL_SECONDS = 300


class PowDisabled(Exception):
    """No `cli_pow_secret` configured — the gate cannot operate (→ 503)."""


class PowRejected(Exception):
    """A submitted PoW header is malformed / forged / expired / replayed / too
    weak (→ 403)."""


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _payload_bytes(exp: int, nonce: str) -> bytes:
    """The canonical compact, key-sorted JSON payload bytes (see byte-layout #1)."""
    return json.dumps({"exp": exp, "nonce": nonce}, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def _mac(secret: str, payload: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _leading_zero_bits(digest: bytes) -> int:
    """Count most-significant leading zero bits of a byte string."""
    bits = 0
    for byte in digest:
        if byte == 0:
            bits += 8
            continue
        bits += 8 - byte.bit_length()
        break
    return bits


def issue_challenge() -> tuple[str, int, datetime]:
    """Mint a fresh signed challenge. Returns `(challenge, difficulty, expires_at)`.

    Raises `PowDisabled` when no secret is configured (the route maps it to 503).
    """
    settings = get_settings()
    if not settings.cli_pow_secret:
        raise PowDisabled("CLI Proof-of-Work secret is not configured")
    expires_at = datetime.now(UTC) + timedelta(seconds=CHALLENGE_TTL_SECONDS)
    exp = int(expires_at.timestamp())
    nonce = secrets.token_hex(16)
    payload = _payload_bytes(exp, nonce)
    mac = _mac(settings.cli_pow_secret, payload)
    challenge = f"{_b64url(payload)}.{mac}"
    return challenge, settings.cli_pow_difficulty, expires_at


async def verify_pow(header: str | None, session: AsyncSession) -> None:
    """Verify a `X-SaferSkills-CLI-PoW` header. Returns None on success.

    Raises `PowDisabled` (→503) when no secret is configured, or `PowRejected`
    (→403) for any malformed / forged / expired / replayed / under-difficulty
    header. Single-use is enforced with `INSERT ... ON CONFLICT DO NOTHING` — a
    replay inserts 0 rows and is rejected, silently (no duplicate-key ERROR in
    the Postgres log) and without dirtying the transaction.
    """
    settings = get_settings()
    if not settings.cli_pow_secret:
        raise PowDisabled("CLI Proof-of-Work secret is not configured")
    if not header:
        raise PowRejected("missing PoW header")

    # header = challenge "." solution ; challenge = payload_b64 "." mac
    challenge, sep, solution = header.rpartition(".")
    if not sep or not challenge or not solution:
        raise PowRejected("malformed PoW header")
    payload_b64, sep2, mac = challenge.rpartition(".")
    if not sep2 or not payload_b64 or not mac:
        raise PowRejected("malformed PoW challenge")

    # 1. Signature — constant-time compare over the decoded payload.
    try:
        payload = _b64url_decode(payload_b64)
    except (ValueError, TypeError) as exc:
        raise PowRejected("undecodable PoW payload") from exc
    expected_mac = _mac(settings.cli_pow_secret, payload)
    if not hmac.compare_digest(expected_mac, mac):
        raise PowRejected("bad PoW signature")

    # 2. Expiry.
    try:
        data = json.loads(payload)
        exp = int(data["exp"])
    except (ValueError, KeyError, TypeError) as exc:
        raise PowRejected("malformed PoW payload") from exc
    now = int(datetime.now(UTC).timestamp())
    if exp < now:
        raise PowRejected("expired PoW challenge")

    # 3. Difficulty — leading zero BITS of sha256(challenge + solution) (NO dot
    #    between them — the '.' lives only in the header, not the hashed bytes).
    digest = hashlib.sha256((challenge + solution).encode("ascii")).digest()
    if _leading_zero_bits(digest) < settings.cli_pow_difficulty:
        raise PowRejected("PoW solution does not meet difficulty")

    # 4. Single-use — claim the challenge hash via INSERT ... ON CONFLICT DO
    #    NOTHING. A replay conflicts → 0 rows inserted → reject. This is silent
    #    (no server-side duplicate-key ERROR log, unlike catching IntegrityError)
    #    and never dirties the transaction (no savepoint needed). The row is
    #    committed by the caller's downstream commit (the rate-limit upsert).
    challenge_sha256 = hashlib.sha256(challenge.encode("ascii")).hexdigest()
    expires_at = datetime.fromtimestamp(exp, tz=UTC)
    stmt = (
        pg_insert(CliPowSpent)
        .values(challenge_sha256=challenge_sha256, expires_at=expires_at)
        .on_conflict_do_nothing(index_elements=["challenge_sha256"])
        .returning(CliPowSpent.challenge_sha256)
    )
    inserted = (await session.execute(stmt)).first()
    if inserted is None:
        # Conflict → 0 rows returned → this challenge was already spent.
        raise PowRejected("PoW challenge already spent")
