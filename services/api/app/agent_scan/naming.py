"""Memorable agent-scan codenames (`swift-otter`) — server-side.

Replaces the old `my-agent` placeholder for the bootstrap path: the web
`/agents/scan` picker and any direct API caller that omits `agent_name` now get a
distinct, human-rememberable card instead of a shared placeholder. The `saferskills`
CLI generates + persists its own per-machine codename and sends it explicitly, so
this generator only fires when no name is supplied.

`secrets.choice` keeps the pick uniform. There is no persistence — the server has
no stable per-caller identity to key on, so a fresh codename per nameless call is
the contract (mirrors the CLI's "Web/API → server-gen" behaviour).
"""

from __future__ import annotations

import secrets

# Max display-name length (mirrors the `agent_name` `max_length=200` wire bound).
_MAX_NAME_LEN = 200

_ADJECTIVES = (
    "swift",
    "lucid",
    "amber",
    "quiet",
    "brave",
    "clever",
    "cosmic",
    "golden",
    "hidden",
    "jolly",
    "keen",
    "lively",
    "mellow",
    "nimble",
    "polar",
    "rapid",
    "royal",
    "sage",
    "silent",
    "solar",
    "stellar",
    "sturdy",
    "sunny",
    "vivid",
    "witty",
    "zesty",
    "bold",
    "bright",
    "crisp",
    "daring",
    "eager",
    "fancy",
    "gentle",
    "humble",
    "ivory",
    "lunar",
    "merry",
    "noble",
    "plucky",
    "proud",
    "rustic",
    "shiny",
    "spry",
    "tidy",
    "urban",
    "valiant",
    "wily",
    "zen",
)

_NOUNS = (
    "otter",
    "falcon",
    "heron",
    "badger",
    "lynx",
    "marten",
    "gecko",
    "ibis",
    "koala",
    "lemur",
    "manta",
    "narwhal",
    "ocelot",
    "panther",
    "quokka",
    "raven",
    "salmon",
    "tapir",
    "urchin",
    "vulture",
    "walrus",
    "yak",
    "zebra",
    "beaver",
    "cobra",
    "dingo",
    "egret",
    "ferret",
    "gibbon",
    "hawk",
    "jackal",
    "kestrel",
    "llama",
    "magpie",
    "newt",
    "osprey",
    "puffin",
    "quail",
    "rabbit",
    "seal",
    "toucan",
    "urial",
    "viper",
    "weasel",
    "wombat",
    "fox",
    "mole",
    "owl",
)


def generate_codename() -> str:
    """A fresh `adjective-noun` codename, e.g. `lucid-falcon`."""
    return f"{secrets.choice(_ADJECTIVES)}-{secrets.choice(_NOUNS)}"


def resolve_agent_name(name: str | None) -> str:
    """Honour a caller-supplied name (trimmed, ≤200 chars); else a fresh codename."""
    if name is not None:
        trimmed = name.strip()
        if trimmed:
            return trimmed[:_MAX_NAME_LEN]
    return generate_codename()
