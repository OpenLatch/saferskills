"""Pack signing — sign the served bytes; verify with the served pubkey (I-5.5)."""

from __future__ import annotations

import base64

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.agent_scan import signing
from app.core.config import get_settings


def _set_key(monkeypatch: pytest.MonkeyPatch) -> Ed25519PrivateKey:
    sk = Ed25519PrivateKey.generate()
    seed_b64 = base64.b64encode(sk.private_bytes_raw()).decode()
    monkeypatch.setattr(get_settings(), "saferskills_pack_signing_key", seed_b64)
    return sk


def test_sign_then_verify_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_key(monkeypatch)
    body = b'{"pack":"bytes"}'
    key_id, sig = signing.sign_pack(body)
    assert key_id == signing.KEY_ID
    assert sig

    keys = signing.public_keys()
    pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(keys[key_id]))
    pub.verify(base64.b64decode(sig), body)  # no raise == valid


def test_tampered_body_fails_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_key(monkeypatch)
    body = b'{"pack":"bytes"}'
    key_id, sig = signing.sign_pack(body)
    pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(signing.public_keys()[key_id]))
    with pytest.raises(InvalidSignature):
        pub.verify(base64.b64decode(sig), body + b"X")


def test_unset_key_yields_empty_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "saferskills_pack_signing_key", None)
    assert signing.sign_pack(b"x") == ("", "")
    assert signing.public_keys() == {}
