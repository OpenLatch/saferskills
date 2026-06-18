"""Unit: server-side agent-scan codename generation.

Pins the `my-agent` placeholder replacement — `resolve_agent_name(None)` yields a
fresh `adjective-noun` codename (never the old placeholder), an explicit name is
honoured (trimmed + length-capped), and `generate_codename` stays in-vocabulary.
"""

from __future__ import annotations

from app.agent_scan.naming import generate_codename, resolve_agent_name


def test_generate_codename_has_adjective_noun_shape() -> None:
    for _ in range(50):
        name = generate_codename()
        adj, sep, noun = name.partition("-")
        assert sep == "-"
        assert adj.isalpha() and noun.isalpha()
        assert name == name.lower()


def test_resolve_honours_explicit_name() -> None:
    assert resolve_agent_name("prod-bot") == "prod-bot"
    assert resolve_agent_name("  spaced  ") == "spaced"


def test_resolve_caps_length_at_200() -> None:
    assert len(resolve_agent_name("x" * 300)) == 200


def test_resolve_generates_for_missing_or_blank() -> None:
    for value in (None, "", "   "):
        name = resolve_agent_name(value)
        assert name != "my-agent"
        assert "-" in name
