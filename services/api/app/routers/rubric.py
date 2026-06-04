"""Rubric content surface — `GET /api/v1/rubric/content` (D-05-32).

Serves the explainable-finding prose map (rule_id → title / explanation /
remediation) the install CLI caches for offline finding display. The payload is
loaded once at import from `app/generated/rule_content.json` (codegen step 7,
emitted from the same `rubric/**` frontmatter as the webapp `content.ts`).

Unauthenticated + uncapped (D-05-09) — same posture as every other CLI read.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Response

from app.schemas.rubric import RubricContentResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rubric", tags=["rubric"])

_CONTENT_PATH = Path(__file__).resolve().parent.parent / "generated" / "rule_content.json"


@lru_cache(maxsize=1)
def _load_content() -> RubricContentResponse:
    """Load + validate the generated rule-content map once (cached for process life).

    Fail-open: any read/parse error degrades to an empty map (the CLI then falls
    back to rule_id + remediation_link). A single broad catch is deliberate — and
    avoids an `except (OSError, ValueError):` tuple, which `ruff format` on this
    toolchain rewrites into the invalid Py2 `except OSError, ValueError:` form
    (see .claude rules / project verify gotchas).
    """
    # Broad catch is intentional fail-open (read/decode/validate errors all → empty).
    try:
        raw = json.loads(_CONTENT_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("rubric.content.missing", extra={"path": str(_CONTENT_PATH)})
        return RubricContentResponse(rubric_version="unknown", rules={})
    return RubricContentResponse.model_validate(raw)


@router.get(
    "/content",
    response_model=RubricContentResponse,
    summary="Explainable-finding content map (offline CLI prose).",
)
async def get_rubric_content(response: Response) -> RubricContentResponse:
    # Immutable per rubric_version → cache hard; the CLI refetches only when the
    # version it has cached differs from a scan report's rubric_version.
    response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
    return _load_content()
