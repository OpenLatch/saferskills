"""Per-run pack assembly — placeholders substituted, exact-bytes serialize."""

from __future__ import annotations

import json

from app.agent_scan.canary import derive_seed
from app.agent_scan.pack import RESULT_SCHEMA, assemble_pack, load_pack_source

_MK = b"0123456789abcdef0123456789abcdef"


def test_pack_source_is_the_full_baseline() -> None:
    src = load_pack_source()
    assert src["packId"] == "saferskills-agent-baseline"
    assert len(src["tests"]) == 20


def test_assemble_substitutes_every_placeholder() -> None:
    seed = derive_seed(_MK, "run-1", "nonce-1")
    body = assemble_pack(seed=seed, decoy="OL-DECOY-zzz")
    text = body.decode()

    # No unsubstituted placeholder survives into the served bytes.
    assert "{{CANARY}}" not in text
    assert "{{CANARY:" not in text
    assert "{{DECOY}}" not in text

    data = json.loads(body)
    assert data["result_schema"] == RESULT_SCHEMA
    assert data["key_id"] == "saferskills-agent-pack-2026"
    assert data["trust_tier"] == "cloud_validated_client_administered"
    assert len(data["tests"]) == 20
    # AS-06's honeytoken {{CANARY}} became a tagged per-run canary.
    assert "OL-AS-06-" in text


def test_assemble_is_deterministic_for_one_run() -> None:
    seed = derive_seed(_MK, "run-1", "nonce-1")
    a = assemble_pack(seed=seed, decoy="OL-DECOY-zzz")
    b = assemble_pack(seed=seed, decoy="OL-DECOY-zzz")
    assert a == b  # byte-for-byte (the client verifies these exact bytes)
