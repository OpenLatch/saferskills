"""GitHub webhook router.

Mounted WITHOUT the /api/v1 prefix so the endpoint is POST /webhooks/github.

Verifies X-Hub-Signature-256 via the GithubSkillsWebhookAdapter classmethod.
Routes push/repository events for the configured repo (`discovery.repo_full_name`)
to the Procrastinate ingest task. Ping events are acknowledged; all other events
are silently ignored (202).
"""

from __future__ import annotations

from typing import Any, cast

import structlog
from fastapi import APIRouter, Header, HTTPException, Request, status

from app.ingestion.sources.github_skills_webhook import GithubSkillsWebhookAdapter

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.post("/webhooks/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
    x_github_event: str | None = Header(default=None, alias="X-GitHub-Event"),
    x_github_delivery: str | None = Header(default=None, alias="X-GitHub-Delivery"),
) -> dict[str, str | None]:
    """Handle GitHub push/repository/ping webhooks for the skills repo."""
    raw_body = await request.body()

    if not GithubSkillsWebhookAdapter.verify_signature(raw_body, x_hub_signature_256):
        logger.warning(
            "webhooks.github.bad_signature",
            delivery=x_github_delivery,
            event=x_github_event,
        )
        raise HTTPException(status_code=403, detail="invalid signature")

    if x_github_event not in {"push", "repository", "ping"}:
        return {"status": "ignored", "event": x_github_event}

    if x_github_event == "ping":
        return {"status": "ok", "event": "ping", "delivery": x_github_delivery}

    # Parse body only after signature is verified.
    _cached: Any = request.state.__dict__.get("_json")
    payload: dict[str, Any] = cast("dict[str, Any]", _cached) if isinstance(_cached, dict) else {}
    if not payload:
        try:
            json_body: Any = await request.json()
            payload = cast("dict[str, Any]", json_body) if isinstance(json_body, dict) else {}
        except Exception:
            payload = {}

    from app.ingestion.config.loader import get_source_config

    cfg = get_source_config("github_skills")
    repo_full_name: str = cfg.discovery.get("repo_full_name", "anthropics/skills")

    _repo_raw: Any = payload.get("repository")
    repo_obj: dict[str, Any] = (
        cast("dict[str, Any]", _repo_raw) if isinstance(_repo_raw, dict) else {}
    )
    incoming_repo: str = str(repo_obj.get("full_name") or "")
    if incoming_repo != repo_full_name:
        # Webhook from an unexpected repo — ignore.
        logger.info(
            "webhooks.github.unexpected_repo",
            incoming=incoming_repo,
            expected=repo_full_name,
        )
        return {"status": "ignored", "event": x_github_event}

    from app.ingestion.enqueue import enqueue_ingest_task

    await enqueue_ingest_task.defer_async(source="github_skills", raw_payload=payload)

    logger.info(
        "webhooks.github.queued",
        repo=incoming_repo,
        event=x_github_event,
        delivery=x_github_delivery,
    )
    return {"status": "queued", "event": x_github_event, "delivery": x_github_delivery}
