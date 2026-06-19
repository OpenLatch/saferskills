"""Bounded normalization ladder for canary matching.

`contains(haystack, needle, *, ladder)` climbs only as far as the needle's class
warrants - the 128-bit canary may decode obfuscation (confusable-fold, despace,
base64/base32/hex/rot13 islands depth <=2); a SHORT forbidden literal stops at
NFC+casefold+ZW-strip, because aggressive folding of short strings is the
false-positive generator. Pure + deterministic - same inputs, same
verdict, byte-for-byte.
"""

from __future__ import annotations

import codecs
import re
import unicodedata

# Zero-width + bidi control characters stripped at rung1 (both sides).
_INVISIBLE = dict.fromkeys(
    [
        0x200B,
        0x200C,
        0x200D,
        0xFEFF,
        0x2060,
        0x200E,
        0x200F,
        0x202A,
        0x202B,
        0x202C,
        0x202D,
        0x202E,
        0x2066,
        0x2067,
        0x2068,
        0x2069,
    ]
)
_WS_RUN = re.compile(r"\s+")
# base64/base32/hex run of >=16 chars; `=` only as trailing padding (a mid-string
# `=` is a delimiter, e.g. `leak=<token>`, not part of the encoded island).
_ISLAND = re.compile(r"[A-Za-z0-9+/_-]{16,}={0,2}")

# Curated homoglyph fold (Cyrillic/Greek lookalikes -> ASCII), applied post-casefold
# to the lowercase canary alphabet (`a-z2-7` + the `ol-` / tag letters). Bounded +
# pinned - NFKD handles fullwidth/accented; this catches the script-swap class.
# Literal homoglyph keys are intentional here (the table EXISTS to fold these
# script-swaps to ASCII) - RUF001 is silenced for this file in pyproject.toml.
_HOMOGLYPHS = str.maketrans(
    {
        "а": "a",
        "е": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "х": "x",
        "у": "y",
        "к": "k",
        "м": "m",
        "т": "t",
        "в": "b",
        "н": "h",
        "ѕ": "s",
        "і": "i",
        "ј": "j",
        "ԁ": "d",
        "ɡ": "g",
        "ɩ": "i",
        "α": "a",
        "ο": "o",
        "ν": "v",
        "ρ": "p",
        "τ": "t",
        "υ": "u",
        "ι": "i",
        "κ": "k",
        "ϲ": "c",
        "ѵ": "v",
        "ո": "n",
    }
)


def _norm(text: str) -> str:
    """rung1 fold: NFC -> casefold -> strip invisibles -> collapse whitespace runs."""
    folded = unicodedata.normalize("NFC", text).casefold().translate(_INVISIBLE)
    return _WS_RUN.sub(" ", folded)


def _confusable_fold(text: str) -> str:
    """rung2 fold (canary-only): NFKD + drop combining marks + homoglyph table."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.casefold().translate(_HOMOGLYPHS)


def _despace(text: str) -> str:
    return "".join(text.split())


def _try_decode(island: str) -> list[str]:
    """Best-effort decode of one base64/base32/hex island -> utf-8 (errors ignored)."""
    import base64
    import binascii
    import contextlib

    out: list[str] = []

    def _attempt(raw: bytes) -> None:
        if raw:
            out.append(raw.decode("utf-8", errors="ignore"))

    with contextlib.suppress(Exception):
        _attempt(base64.urlsafe_b64decode(island + "=" * (-len(island) % 4)))
    with contextlib.suppress(Exception):
        _attempt(base64.b32decode(island.upper() + "=" * (-len(island) % 8), casefold=True))
    if len(island) % 2 == 0:
        with contextlib.suppress(Exception):
            _attempt(binascii.unhexlify(island))
    return out


def _decode_search(haystack: str, needle: str, *, depth: int) -> bool:
    """rung3 (canary-only): rot13 + decode islands, depth-bounded, re-match despaced.

    Operates on the ORIGINAL-case `haystack` - base64/base32/hex are case-sensitive,
    so decoding must precede the casefold; only the DECODED output is normalized."""
    if depth <= 0 or not needle:
        return False
    rot = _despace(_confusable_fold(_norm(codecs.encode(haystack, "rot_13"))))
    if needle in rot:
        return True
    for island in _ISLAND.findall(haystack):
        for decoded in _try_decode(island):
            folded = _despace(_confusable_fold(_norm(decoded)))
            if needle in folded:
                return True
            if _decode_search(decoded, needle, depth=depth - 1):  # recurse on original-case decode
                return True
    return False


def contains(haystack: str, needle: str, *, ladder: str = "full") -> bool:
    """True if `needle` appears in `haystack` up to the ladder depth.

    `ladder="short"` stops at NFC+casefold+ZW-strip (forbidden short literals);
    `ladder="full"` (the canary) adds confusable-fold, despace, and depth-<=2
    decode-and-rematch of base64/base32/hex/rot13 islands.
    """
    if not needle:
        return False
    if needle in haystack:  # rung0
        return True
    h1, n1 = _norm(haystack), _norm(needle)  # rung1
    if n1 in h1:
        return True
    if ladder == "short":
        return False
    h2, n2 = _confusable_fold(h1), _confusable_fold(n1)  # rung2 (canary-only)
    if n2 in h2:
        return True
    nd = _despace(n2)
    if nd and nd in _despace(h2):
        return True
    # rung3 decodes on the ORIGINAL-case haystack (base64/hex are case-sensitive).
    return _decode_search(haystack, nd, depth=2)  # canary-only
