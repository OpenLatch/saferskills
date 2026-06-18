"""Per-run pack assembly.

Loads the generated backend pack source (`app/generated/agent_pack.json`,
placeholders intact), substitutes the per-run minted canaries + decoy into every
test, and serializes the per-run "official" pack to the EXACT bytes the route
signs + serves (`signing.sign_pack`). No JCS — the server is the sole serializer;
the client verifies these exact received bytes.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from app.agent_scan import signing
from app.agent_scan.canary import canary

_PACK_PATH = Path(__file__).resolve().parents[1] / "generated" / "agent_pack.json"

# {{CANARY}} | {{CANARY:slot}} ; {{DECOY}} handled separately.
_CANARY_RE = re.compile(r"\{\{CANARY(?::([A-Za-z0-9_-]+))?\}\}")

RESULT_SCHEMA = "agent_scan_result.v1"
TRUST_TIER = "cloud_validated_client_administered"
TELEMETRY_NOTICE = (
    "SaferSkills records anonymous company-level signals (network ASN + a "
    "server-derived fingerprint, never a raw IP or any personal data) to improve "
    "the service. Opt out with --no-telemetry, CI, DO_NOT_TRACK, or "
    "SAFERSKILLS_NO_TELEMETRY."
)


@lru_cache(maxsize=1)
def load_pack_source() -> dict[str, Any]:
    """The generated backend pack source (cached). Placeholders intact."""
    return json.loads(_PACK_PATH.read_text(encoding="utf-8"))


def _substitute_str(text: str, seed: bytes, decoy: str, tag: str) -> str:
    def _repl(m: re.Match[str]) -> str:
        slot = m.group(1) or tag
        return canary(seed, slot, tag)

    return _CANARY_RE.sub(_repl, text).replace("{{DECOY}}", decoy)


def _substitute(value: Any, seed: bytes, decoy: str, tag: str) -> Any:
    """Deep-substitute placeholders in every string within a test object."""
    if isinstance(value, str):
        return _substitute_str(value, seed, decoy, tag)
    if isinstance(value, list):
        return [_substitute(v, seed, decoy, tag) for v in cast("list[Any]", value)]
    if isinstance(value, dict):
        return {
            k: _substitute(v, seed, decoy, tag) for k, v in cast("dict[str, Any]", value).items()
        }
    return value


def assemble_pack(*, seed: bytes, decoy: str) -> bytes:
    """Assemble the per-run official pack and return the EXACT bytes to sign+serve."""
    source = load_pack_source()
    tests: list[dict[str, Any]] = []
    required: set[str] = set()
    optional: set[str] = set()
    for test in source["tests"]:
        tag = test["testId"]
        tests.append(_substitute(test, seed, decoy, tag))
        if test["tier"] == "launch":
            required.add(test["requiredCapability"])
        else:
            optional.add(test["requiredCapability"])

    pack = {
        "pack_id": source["packId"],
        "pack_version": source["packVersion"],
        "key_id": signing.KEY_ID,
        "trust_tier": TRUST_TIER,
        "telemetry_notice": TELEMETRY_NOTICE,
        "required_capabilities": sorted(required),
        "optional_capabilities": sorted(optional - required),
        "tests": tests,
        "result_schema": RESULT_SCHEMA,
    }
    # Deterministic, compact — the exact served bytes the client verifies.
    return json.dumps(pack, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
