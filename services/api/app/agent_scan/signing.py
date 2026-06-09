"""Pack signing — sign the exact served bytes (I-5.5, D-5.5-13, lean crypto).

One Ed25519 key. On a pack fetch the route assembles the per-run pack JSON,
serializes to bytes, and signs THOSE EXACT BYTES; the client verifies the exact
received bytes (`verify_strict`) — no JCS, no canonicalization, no re-serialize.
The signature + key_id + sha256 of the served bytes are archived per run so the
pack re-verifies later.

Lean posture: ONE key (`key_id = saferskills-agent-pack-2026`), a flat
`{key_id: base64-pubkey}` map served at `GET /api/v1/agent-pack/keys`, NO JWKS /
`.well-known` / rotation machinery. Rotation later = add a second map entry + bake
the new pubkey in the next CLI release.

Degradation: `SAFERSKILLS_PACK_SIGNING_KEY` unset (dev/test/CI) → `sign_pack`
returns `("", "")` and the route omits the signature header (the run is labeled
`manual-bootstrap`). The `config.py` startup guard hard-fails boot in
staging/production so this never happens on a real deploy.
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.config import get_settings

# Single launch key id. Rotation = add a second entry to the served map + bake
# the new pubkey; the old key stays until old packs age out (D-5.5-10).
KEY_ID = "saferskills-agent-pack-2026"


def _load_private() -> Ed25519PrivateKey | None:
    raw = get_settings().saferskills_pack_signing_key
    if not raw:
        return None
    seed = base64.b64decode(raw)
    return Ed25519PrivateKey.from_private_bytes(seed)


def sign_pack(body: bytes) -> tuple[str, str]:
    """Sign the exact served bytes. Returns `(key_id, base64(sig))`, or `("", "")`
    when no signing key is configured (dev/test — the route then omits the header)."""
    priv = _load_private()
    if priv is None:
        return ("", "")
    sig = priv.sign(body)
    return (KEY_ID, base64.b64encode(sig).decode("ascii"))


def public_keys() -> dict[str, str]:
    """Flat `{key_id: base64(raw-pubkey)}` map for `GET /api/v1/agent-pack/keys`.

    Config-sourced (derived from the private key) — no DB. Empty when no key is
    configured. The same base64 pubkey string is what the CLI bakes (outbox/01).
    """
    priv = _load_private()
    if priv is None:
        return {}
    pub = priv.public_key().public_bytes_raw()
    return {KEY_ID: base64.b64encode(pub).decode("ascii")}
