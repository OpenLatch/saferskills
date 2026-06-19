"""Install-telemetry intake — `POST /api/v1/installs`.

The install CLI reports a successful install here, but ONLY when the user has
opted in (first-run consent; off by default, skipped in CI/non-TTY). One row is
written to the dedicated `install_events` store; the GROUP-BY aggregate on the
item-detail surface then reflects real adoption instead of the mock.

Closed-enum agent + kind, no PII. The submitter IP is redacted to /24 (v4) or
/48 (v6) at write time (privacy.md) — a raw IP is never stored. Unauthenticated
(like every CLI endpoint); low-volume + opt-in so it shares no rate bucket, but
it fails closed on an unknown slug (404) and never echoes input back.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access_log_middleware import redact_ip
from app.db.session import get_session
from app.models.catalog_item import CatalogItem
from app.models.install_event import InstallEvent
from app.observability.events import emit_install_reported
from app.schemas.installs import InstallReportRequest

router = APIRouter(prefix="/installs", tags=["installs"])


@router.post("", status_code=204, summary="Report an opt-in install (CLI).")
async def report_install(
    payload: InstallReportRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> None:
    # Public-only: an install can only be reported against a public catalog item.
    item_id = (
        await session.execute(
            select(CatalogItem.id).where(
                CatalogItem.slug == payload.slug, CatalogItem.visibility == "public"
            )
        )
    ).scalar_one_or_none()
    if item_id is None:
        raise HTTPException(status_code=404, detail="item_not_found")

    client_host = request.client.host if request.client else None
    session.add(
        InstallEvent(
            catalog_item_id=item_id,
            agent=payload.agent,
            kind=payload.kind,
            cli_version=payload.cli_version,
            redacted_ip=redact_ip(client_host),
        )
    )
    await session.commit()

    emit_install_reported(agent=payload.agent, kind=payload.kind)
