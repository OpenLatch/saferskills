"""GET /api/v1/community/slack/redirect — stable hop to the live Slack invite.

The configured never-expire invite URL (`SLACK_INVITE_URL`) is held server-side,
so rotating a dead link is a one-value change with no code / redirect-chain edit.
The webapp `/slack` pretty URL 302s here; this 302s on to the invite.

302 (not 301): the target rotates, and a 301 gets cached by browsers/proxies, so
a future link rotation would be silently bypassed.

`join.slack.com` is a fixed, non-user-controlled host (the URL is validated to an
`https://*.slack.com` host at config load — `config.py::_validate_slack_invite_url`),
so this server-initiated fetch is outside the github-only SSRF concern
(`.claude/rules/security.md` § Public-input handling #2).
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app.core.config import get_settings

router = APIRouter(tags=["community"])


@router.get("/community/slack/redirect", summary="Redirect to the community Slack invite")
async def slack_redirect() -> RedirectResponse:
    """302 to the configured Slack invite, or 503 when it is unset."""
    url = get_settings().slack_invite_url
    if url is None:
        raise HTTPException(status_code=503, detail="Slack invite is not configured.")
    return RedirectResponse(url, status_code=302)
