"""Per-run canary derivation (I-5.5)."""

from __future__ import annotations

import base64
import codecs
import re

from app.agent_scan.canary import canary, derive_seed, expected_transform, new_decoy

_MK = b"0123456789abcdef0123456789abcdef"


def test_two_runs_produce_different_canaries() -> None:
    s1 = derive_seed(_MK, "run-A", "n1")
    s2 = derive_seed(_MK, "run-B", "n1")
    assert s1 != s2
    assert canary(s1, "AS-01", "AS-01") != canary(s2, "AS-01", "AS-01")
    # Same run_id, different nonce → different too (per-run rotation).
    assert derive_seed(_MK, "run-A", "n2") != s1


def test_derivation_is_deterministic() -> None:
    assert derive_seed(_MK, "r", "n") == derive_seed(_MK, "r", "n")
    seed = derive_seed(_MK, "r", "n")
    assert canary(seed, "AS-01", "AS-01") == canary(seed, "AS-01", "AS-01")


def test_canary_shape_is_tagged_base32() -> None:
    c = canary(derive_seed(_MK, "r", "n"), "AS-06", "AS-06")
    assert c.startswith("OL-AS-06-")
    suffix = c[len("OL-AS-06-") :]
    assert re.fullmatch(r"[A-Z2-7]+", suffix)  # RFC-4648 base32, no padding


def test_expected_transform_round_trips() -> None:
    v = "OL-AS-02-ABCDEF234567"
    assert base64.b64decode(expected_transform(v, "base64")).decode() == v
    assert bytes.fromhex(expected_transform(v, "hex")).decode() == v
    assert codecs.decode(expected_transform(v, "rot13"), "rot_13") == v
    assert expected_transform(v, "whitespace") == " ".join(v)


def test_decoy_is_unique_and_tagged() -> None:
    d1, d2 = new_decoy(), new_decoy()
    assert d1 != d2
    assert d1.startswith("OL-DECOY-")
