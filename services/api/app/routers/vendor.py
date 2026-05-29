"""Vendor right-of-reply surface — verify-by-repo-file + public response.

Implements the I-02 vendor-verification flow (D-05..D-08) + the PRD §4.11 web
form. Three-step verification with **no token ever in a URL**:

1. `POST /items/<slug>/vendor/verify/start` — issue a one-time verification
   token; the SHA-256 hash is persisted on a `vendor_verifications` row. The
   raw token is returned once in the JSON body for the vendor to commit.
2. `POST /items/<slug>/vendor/verify/redeem` — fetch
   `raw.githubusercontent.com/<org>/<repo>/<branch>/.saferskills/verify.txt`,
   match it against the issued token, mark the verification redeemed, and mint
   a short-lived (15 min) HS256 session JWT. The JWT is returned as JSON — the
   **webapp** owns the `ss_vendor_session` HttpOnly cookie (same-origin), this
   API is the sole JWT *verifier*.
3. `GET /items/<slug>/vendor/session` — the webapp forwards the cookie's JWT as
   a Bearer token here so the SSR page can branch verified/unverified without
   holding the signing secret.

`POST /items/<slug>/vendor/responses` accepts the verified Bearer JWT + a
≤2000-char Markdown body, inserts a `vendor_responses` row, and optionally
enqueues an immediate re-scan.

Security: `raw.githubusercontent.com` is on the outbound allowlist
(`.claude/rules/security.md` § Public-input). The verify URL is built from the
stored `(github_org, github_repo, default_branch)` — never from free-text — so
there is no SSRF surface.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.models.catalog_item import CatalogItem
from app.models.vendor import VendorResponse, VendorVerification
from app.observability import events
from app.schemas.orm_base import OrmBaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/items", tags=["vendor"])

VERIFY_FILE_PATH = ".saferskills/verify.txt"
TOKEN_TTL = timedelta(hours=1)
SESSION_TTL_SECONDS = 900  # 15 minutes
RAW_FETCH_TIMEOUT = 10.0
MAX_VERIFY_FILE_BYTES = 4096
JWT_ALGORITHM = "HS256"


# ── Wire DTOs (hand-written endpoint shapes) ─────────────────────────────────


class VerifyStartResponse(OrmBaseModel):
    token: str
    expires_at: datetime
    file_path: str


class VerifyRedeemRequest(OrmBaseModel):
    token: str = Field(..., min_length=8, max_length=128)
    github_user: str = Field(..., min_length=1, max_length=100)


class VerifyRedeemResponse(OrmBaseModel):
    session_jwt: str
    github_user: str
    expires_at: datetime


class VendorSessionResponse(OrmBaseModel):
    verified: bool
    github_user: str | None = None


class VendorResponseRequest(OrmBaseModel):
    body_markdown: str = Field(..., min_length=1, max_length=2000)
    trigger_rescan: bool = False


class VendorResponseResult(OrmBaseModel):
    ok: bool
    response_id: str
    version: int
    rescan_triggered: bool


# ── Helpers ──────────────────────────────────────────────────────────────────


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mint_session_jwt(*, slug: str, github_user: str, verification_id: UUID) -> tuple[str, datetime]:
    now = int(time.time())
    exp = now + SESSION_TTL_SECONDS
    payload = {
        "sub": "vendor",
        "slug": slug,
        "gh": github_user,
        "vid": str(verification_id),
        "iat": now,
        "exp": exp,
    }
    token = jwt.encode(  # pyright: ignore[reportUnknownMemberType]
        payload, get_settings().vendor_session_secret, algorithm=JWT_ALGORITHM
    )
    return token, datetime.fromtimestamp(exp, tz=UTC)


def _decode_session_jwt(authorization: str | None, *, slug: str) -> dict[str, str] | None:
    """Verify a `Authorization: Bearer <jwt>` header against the slug.

    Returns the decoded payload on success, or None if the header is missing,
    malformed, expired, badly signed, or scoped to a different slug.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    if not token:
        return None
    try:
        payload = jwt.decode(  # pyright: ignore[reportUnknownMemberType]
            token,
            get_settings().vendor_session_secret,
            algorithms=[JWT_ALGORITHM],
        )
    except jwt.PyJWTError:
        return None
    if payload.get("sub") != "vendor" or payload.get("slug") != slug:
        return None
    return payload


async def _load_item(session: AsyncSession, slug: str) -> CatalogItem:
    item = (
        await session.execute(select(CatalogItem).where(CatalogItem.slug == slug))
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")
    return item


async def _fetch_verify_file(item: CatalogItem) -> str:
    """Fetch `.saferskills/verify.txt` from raw.githubusercontent.com.

    The URL is built entirely from stored, validated repo coordinates — no
    user free-text — so there is no SSRF surface beyond the allowlisted host.
    """
    url = (
        f"https://raw.githubusercontent.com/{item.github_org}/{item.github_repo}"
        f"/{item.default_branch}/{VERIFY_FILE_PATH}"
    )
    async with httpx.AsyncClient(timeout=RAW_FETCH_TIMEOUT, follow_redirects=False) as client:
        resp = await client.get(url)
    if resp.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{VERIFY_FILE_PATH} not found on {item.default_branch}",
        )
    resp.raise_for_status()
    return resp.content[:MAX_VERIFY_FILE_BYTES].decode("utf-8", errors="replace")


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/{slug}/vendor/verify/start", response_model=VerifyStartResponse)
async def verify_start(
    slug: str, session: AsyncSession = Depends(get_session)
) -> VerifyStartResponse:
    item = await _load_item(session, slug)
    token = secrets.token_urlsafe(24)
    expires_at = datetime.now(tz=UTC) + TOKEN_TTL

    verification = VendorVerification(
        catalog_item_id=item.id,
        token_hash_sha256=_hash_token(token),
        expires_at=expires_at,
        state="pending",
    )
    session.add(verification)
    await session.commit()

    return VerifyStartResponse(token=token, expires_at=expires_at, file_path=VERIFY_FILE_PATH)


@router.post("/{slug}/vendor/verify/redeem", response_model=VerifyRedeemResponse)
async def verify_redeem(
    slug: str,
    body: VerifyRedeemRequest,
    session: AsyncSession = Depends(get_session),
) -> VerifyRedeemResponse:
    item = await _load_item(session, slug)

    token_hash = _hash_token(body.token)
    now = datetime.now(tz=UTC)
    verification = (
        await session.execute(
            select(VendorVerification)
            .where(VendorVerification.catalog_item_id == item.id)
            .where(VendorVerification.token_hash_sha256 == token_hash)
            .order_by(desc(VendorVerification.issued_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if verification is None:
        raise HTTPException(status_code=400, detail="unknown or invalid token")
    if verification.expires_at <= now:
        raise HTTPException(status_code=400, detail="verification token expired")

    contents = await _fetch_verify_file(item)
    if body.token not in {line.strip() for line in contents.splitlines()}:
        raise HTTPException(status_code=400, detail="verification file did not contain the token")

    # What's verified is *control of the repo* (the committer pushed the token
    # to the default branch), NOT the identity of a named GitHub user. The
    # `github_user` is a self-reported convenience label only — it must never
    # drive public author attribution (that derives from the verified repo;
    # see `routers/items.py::_vendor_responses`). True identity verification
    # (OAuth + push-permission) lands with auth in I-06.
    verification.state = "verified"
    verification.redeemed_at = now
    verification.verified_github_user = body.github_user  # self-reported, not trusted
    await session.commit()

    events.emit_vendor_verification_succeeded(catalog_item_id=item.id)

    token, expires_at = mint_session_jwt(
        slug=slug, github_user=body.github_user, verification_id=verification.id
    )
    return VerifyRedeemResponse(
        session_jwt=token, github_user=body.github_user, expires_at=expires_at
    )


@router.get("/{slug}/vendor/session", response_model=VendorSessionResponse)
async def vendor_session(
    slug: str, authorization: str | None = Header(default=None)
) -> VendorSessionResponse:
    payload = _decode_session_jwt(authorization, slug=slug)
    if payload is None:
        return VendorSessionResponse(verified=False)
    return VendorSessionResponse(verified=True, github_user=payload.get("gh"))


@router.post("/{slug}/vendor/responses", response_model=VendorResponseResult)
async def submit_response(
    slug: str,
    body: VendorResponseRequest,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> VendorResponseResult:
    payload = _decode_session_jwt(authorization, slug=slug)
    if payload is None:
        raise HTTPException(status_code=401, detail="missing or invalid vendor session")

    item = await _load_item(session, slug)
    try:
        verification_id = UUID(payload["vid"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="malformed vendor session") from exc

    # Confirm the verification still belongs to this item (defence-in-depth).
    verification = (
        await session.execute(
            select(VendorVerification)
            .where(VendorVerification.id == verification_id)
            .where(VendorVerification.catalog_item_id == item.id)
        )
    ).scalar_one_or_none()
    if verification is None:
        raise HTTPException(status_code=401, detail="verification no longer valid")

    next_version = (
        await session.execute(
            select(func.coalesce(func.max(VendorResponse.version), 0) + 1).where(
                VendorResponse.catalog_item_id == item.id
            )
        )
    ).scalar_one()

    response = VendorResponse(
        catalog_item_id=item.id,
        vendor_verification_id=verification_id,
        body_markdown=body.body_markdown,
        version=int(next_version),
    )
    session.add(response)
    await session.commit()

    events.emit_vendor_response_submitted(
        catalog_item_id=item.id, body_length=len(body.body_markdown)
    )

    rescan_triggered = False
    if body.trigger_rescan and item.github_url:
        rescan_triggered = await _enqueue_rescan(session, item, item.github_url)

    return VendorResponseResult(
        ok=True,
        response_id=str(response.id),
        version=int(next_version),
        rescan_triggered=rescan_triggered,
    )


# Hold strong refs to fire-and-forget rescan tasks so the GC can't collect them
# mid-run (cf. asyncio.create_task docs).
_rescan_tasks: set[asyncio.Task[None]] = set()


async def _enqueue_rescan(session: AsyncSession, item: CatalogItem, github_url: str) -> bool:
    """Queue a fresh scan of the item's repo (source=rescan_appeal)."""
    from app.queue.scan_runner import scan_run
    from app.scan import persistence

    settings = get_settings()
    rubric_version = settings.rubric_version or settings.git_sha or "unknown"
    engine_version = settings.engine_version or settings.git_sha or "unknown"
    # A fresh idempotency key (timestamp-salted) so the rescan is never a cache
    # hit against the prior scan.
    idempotency_key = persistence.compute_idempotency_key(
        github_url, ref_sha=secrets.token_hex(20), rubric_version=rubric_version
    )
    scan = await persistence.persist_pending_scan(
        session,
        catalog_item_id=item.id,
        idempotency_key=idempotency_key,
        github_url=github_url,
        rubric_version=rubric_version,
        engine_version=engine_version,
        source="rescan_appeal",
    )
    await session.commit()

    task = asyncio.create_task(scan_run(scan.id, github_url, rubric_version))
    _rescan_tasks.add(task)
    task.add_done_callback(_rescan_tasks.discard)
    return True
