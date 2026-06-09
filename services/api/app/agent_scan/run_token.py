"""One-time run/submit token — stateless HMAC + single-use ledger (I-5.5, D-5.5-11).

Mirrors `app/services/cli_pow.py` in spirit (reuse, no new mechanism). The HMAC
key is derived from the SAME operator master key as the canary seed, via a
distinct HKDF `info` label — one secret covers both (lean).

═══════════════════════════════════════════════════════════════════════════════
EXACT WIRE BYTE-LAYOUT (no CLI mirror needed — the CLI never mints/solves this; it
just carries the token the bootstrap API handed it).
═══════════════════════════════════════════════════════════════════════════════

1. payload = UTF-8 of `json.dumps({"run_id": <uuid>, "purpose": "submit",
   "exp": <int>}, separators=(",", ":"), sort_keys=True)`.
2. mac = hex(HMAC_SHA256(key = HKDF(master_key, info=b"OL-agent-runtoken-v1"),
   msg = payload)).
3. token = f"{base64url(payload)}.{mac}".

VERIFY: rsplit('.', 1) → (payload_b64, mac); recompute mac, constant-time-compare;
check `exp` not passed; check `run_id` matches the route. For SUBMIT also claim
single-use: `INSERT INTO agent_run_token_spent (sha256(token), exp) ON CONFLICT DO
NOTHING` → 0 rows = replay → reject (silent). The PACK fetch + status poll verify
WITHOUT the spend (the agent + the CLI pre-flight each fetch once; the spend
happens only at submit — Codex#1).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_scan.canary import HKDF_SALT
from app.core.config import get_settings
from app.models.agent_run_token_spent import AgentRunTokenSpent

_RUNTOKEN_INFO = b"OL-agent-runtoken-v1"
# Dev/test fallback key when no master key is configured — keeps mint+verify
# self-consistent locally without a secret. The staging/prod startup guard
# requires the real master key, so this fallback can never run on a deploy.
_DEV_KEY = b"OL-agent-runtoken-dev-insecure-do-not-use-in-prod"


class RunTokenError(Exception):
    """A run/submit token is malformed / forged / expired / wrong-run / replayed
    (→ 403)."""


def _runtoken_key() -> bytes:
    raw = get_settings().saferskills_agent_master_key
    if not raw:
        return _DEV_KEY
    master = base64.b64decode(raw)
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=HKDF_SALT, info=_RUNTOKEN_INFO).derive(
        master
    )


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _payload_bytes(run_id: str, exp: int) -> bytes:
    return json.dumps(
        {"run_id": run_id, "purpose": "submit", "exp": exp},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _mac(key: bytes, payload: bytes) -> str:
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def mint_submit_token(run_id: str) -> str:
    """Mint a one-time submit token bound to `run_id`, expiring after the
    configured TTL."""
    ttl = get_settings().agent_run_token_ttl_seconds
    exp = int((datetime.now(UTC) + timedelta(seconds=ttl)).timestamp())
    payload = _payload_bytes(run_id, exp)
    mac = _mac(_runtoken_key(), payload)
    return f"{_b64url(payload)}.{mac}"


def _verify_signature_and_binding(token: str | None, run_id: str) -> str:
    """Shared no-spend checks: HMAC + expiry + run_id binding. Returns the
    sha256(token) hex for the optional single-use claim. Raises RunTokenError."""
    if not token:
        raise RunTokenError("missing run token")
    payload_b64, sep, mac = token.rpartition(".")
    if not sep or not payload_b64 or not mac:
        raise RunTokenError("malformed run token")
    try:
        payload = _b64url_decode(payload_b64)
    except (ValueError, TypeError) as exc:
        raise RunTokenError("undecodable run token") from exc
    if not hmac.compare_digest(_mac(_runtoken_key(), payload), mac):
        raise RunTokenError("bad run token signature")
    try:
        data = json.loads(payload)
        token_run_id = str(data["run_id"])
        exp = int(data["exp"])
    except (ValueError, KeyError, TypeError) as exc:
        raise RunTokenError("malformed run token payload") from exc
    if token_run_id != run_id:
        raise RunTokenError("run token bound to a different run")
    if exp < int(datetime.now(UTC).timestamp()):
        raise RunTokenError("expired run token")
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def verify_run_token(token: str | None, run_id: str) -> None:
    """No-spend verify for the pack fetch + status poll (HMAC + expiry +
    run_id binding). The spend happens only at submit (`verify_submit_token`)."""
    _verify_signature_and_binding(token, run_id)


async def verify_submit_token(token: str | None, run_id: str, session: AsyncSession) -> None:
    """Full verify for SUBMIT: the no-spend checks PLUS a single-use claim. A
    replay inserts 0 rows → reject (silent, no duplicate-key ERROR log)."""
    token_sha256 = _verify_signature_and_binding(token, run_id)
    # exp lives in the (already-verified) payload — re-decode for the ledger TTL.
    payload = json.loads(_b64url_decode(token.rpartition(".")[0]))  # type: ignore[union-attr]
    expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=UTC)
    stmt = (
        pg_insert(AgentRunTokenSpent)
        .values(token_sha256=token_sha256, expires_at=expires_at)
        .on_conflict_do_nothing(index_elements=["token_sha256"])
        .returning(AgentRunTokenSpent.token_sha256)
    )
    inserted = (await session.execute(stmt)).first()
    if inserted is None:
        raise RunTokenError("run token already spent")
