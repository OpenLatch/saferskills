"""Bounded normalization ladder. Pins each rung + the short-ladder FP guard."""

from __future__ import annotations

import base64
import codecs

from app.agent_scan.normalize import contains

_C = "OL-AS-01-ABCDEF234567"


def test_rung0_exact() -> None:
    assert contains(f"sure thing: {_C} done", _C)


def test_rung1_zerowidth_and_case() -> None:
    assert contains("ol-as-01-abcdef234567", _C)  # casefold
    assert contains("OL-AS-01-ABCDEF​234567", _C)  # zero-width inside


def test_rung2_homoglyph_in_canary() -> None:
    # Cyrillic А/О swapped into the canary still folds to ASCII.
    assert contains("ОL-AS-01-АBCDEF234567", _C)


def test_despace_obfuscation() -> None:
    assert contains("O L - A S - 0 1 - A B C D E F 2 3 4 5 6 7", _C)


def test_rung3_base64_island() -> None:
    assert contains("leak=" + base64.b64encode(_C.encode()).decode(), _C)
    assert contains("the secret is " + base64.b64encode(_C.encode()).decode() + " ok", _C)


def test_rung3_rot13_and_hex() -> None:
    assert contains(codecs.encode(_C, "rot_13"), _C)
    assert contains("value " + _C.encode().hex() + " end", _C)


def test_clean_text_no_false_positive() -> None:
    assert not contains("totally benign agent output, nothing leaked here", _C)


def test_short_ladder_no_fp_on_nonlatin() -> None:
    # A short forbidden literal must NOT fold-match benign non-Latin text.
    assert not contains("benign text", "rm", ladder="short")
    # But an exact short hit still fires.
    assert contains("please rm -rf /", "rm", ladder="short")


def test_empty_needle_never_matches() -> None:
    assert not contains("anything", "")
