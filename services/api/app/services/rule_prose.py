"""Server-side rule-prose join for explainable findings.

Loads the generated `rule_id → RuleContent` map from `app/generated/rule_content.json`
once (cached for process life) and exposes `lookup(rule_id)`. The report builders
(`app/scan/report_builder.py`) fold the prose onto each finding so the scan + item
reports carry their own explanations — the install CLI renders straight from the
result and never fetches the full rule corpus.

The JSON is emitted by codegen step 7 (`scripts/generate-methodology.cjs`) from the
SAME `rubric/**` frontmatter that produces the webapp `content.ts`, so the two can
never drift. Report-DTO-only: prose is never persisted on `findings`, never in the
scan trace (security.md § Scan-trace transparency).
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from app.schemas.rule_prose import RuleContent

logger = logging.getLogger(__name__)

_CONTENT_PATH = Path(__file__).resolve().parent.parent / "generated" / "rule_content.json"


@lru_cache(maxsize=1)
def _load_prose_map() -> dict[str, RuleContent]:
    """Load + validate the generated rule-content map once (cached for process life).

    Fail-open: any read/parse/validate error degrades to an empty map (findings
    then render with rule_id + remediation_link only). A single broad catch is
    deliberate — and avoids an `except (OSError, ValueError):` tuple, which
    `ruff format` on this toolchain rewrites into the invalid Py2
    `except OSError, ValueError:` form (see .claude rules / project verify gotchas).
    """
    # Broad catch is intentional fail-open (read/decode/validate errors all → {}).
    try:
        raw = json.loads(_CONTENT_PATH.read_text(encoding="utf-8"))
        rules = raw.get("rules", {})
        return {rule_id: RuleContent.model_validate(content) for rule_id, content in rules.items()}
    except Exception:
        logger.warning("rule_prose.content.missing", extra={"path": str(_CONTENT_PATH)})
        return {}


def lookup(rule_id: str) -> RuleContent | None:
    """Return the prose for `rule_id`, or None when the rule has no content entry."""
    return _load_prose_map().get(rule_id)
