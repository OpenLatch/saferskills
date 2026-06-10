"""Bootstrap-prompt rendering (I-5.5, Phase 3, D-5.5-07).

Loads the per-platform bootstrap template (`app/agent_scan/bootstrap/<platform>.md`,
cached) and substitutes the per-run coordinates. The prompt is **text the agent
runs** - no canaries, no scoring logic (prime invariant #1 / thin client). The
canaries live only in the signed pack the agent fetches at `pack_url`.

Placeholders are `{{UPPER_SNAKE}}` markers (NOT `str.format`) so the literal `{`/`}`
in the prompts' JSON examples never clash with substitution.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.services.agent_compat import ALL_AGENTS

_TEMPLATE_DIR = Path(__file__).resolve().parent / "bootstrap"

# Closed platform set = the 8 canonical agent ids + the platform-agnostic fallback.
PLATFORMS: frozenset[str] = frozenset(ALL_AGENTS) | {"universal"}


class UnknownPlatform(ValueError):
    """The requested bootstrap platform is not in the closed set (→ 422)."""


@lru_cache(maxsize=len(ALL_AGENTS) + 1)
def _load_template(platform: str) -> str:
    """Read + cache one platform template for process life."""
    return (_TEMPLATE_DIR / f"{platform}.md").read_text(encoding="utf-8")


def render(
    platform: str,
    *,
    run_id: str,
    pack_url: str,
    submit_url: str,
    poll_url: str,
    submit_token: str,
    consent: str,
) -> str:
    """Render the platform bootstrap prompt with the per-run coordinates.

    Raises `UnknownPlatform` for a platform outside the closed set.
    """
    if platform not in PLATFORMS:
        raise UnknownPlatform(platform)
    body = _load_template(platform)
    replacements = {
        "{{RUN_ID}}": run_id,
        "{{PACK_URL}}": pack_url,
        "{{SUBMIT_URL}}": submit_url,
        "{{POLL_URL}}": poll_url,
        "{{SUBMIT_TOKEN}}": submit_token,
        "{{CONSENT}}": consent,
    }
    for marker, value in replacements.items():
        body = body.replace(marker, value)
    return body
