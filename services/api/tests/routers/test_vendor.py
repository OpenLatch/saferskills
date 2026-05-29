"""Tests for the vendor right-of-reply router.

Pure-JWT session tests need no DB (the `/vendor/session` endpoint only verifies
the Bearer header). The verify/redeem/response flow tests are DB-backed and run
in the `test-be` CI lane against Postgres.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.catalog_item import CatalogItem
from app.models.scan import Scan
from app.routers import vendor

SeededItem = tuple[CatalogItem, Scan]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_session_no_auth_is_unverified() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/items/acme--widget/vendor/session")
    assert resp.status_code == 200
    assert resp.json() == {"verified": False, "github_user": None}


@pytest.mark.asyncio
async def test_session_valid_jwt_is_verified() -> None:
    token, _exp = vendor.mint_session_jwt(
        slug="acme--widget", github_user="octocat", verification_id=uuid.uuid4()
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/items/acme--widget/vendor/session", headers=_bearer(token))
    body = resp.json()
    assert body["verified"] is True
    assert body["github_user"] == "octocat"


@pytest.mark.asyncio
async def test_session_jwt_for_other_slug_rejected() -> None:
    token, _exp = vendor.mint_session_jwt(
        slug="acme--widget", github_user="octocat", verification_id=uuid.uuid4()
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/items/other--repo/vendor/session", headers=_bearer(token))
    assert resp.json()["verified"] is False


@pytest.mark.asyncio
async def test_session_garbage_token_rejected() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get(
            "/api/v1/items/acme--widget/vendor/session",
            headers=_bearer("not-a-jwt"),
        )
    assert resp.json()["verified"] is False


@pytest.mark.asyncio
async def test_response_submit_without_session_is_401() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/items/acme--widget/vendor/responses",
            json={"body_markdown": "We disagree.", "trigger_rescan": False},
        )
    assert resp.status_code == 401


# ── DB-backed flow ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_start_unknown_item_404(db_client: AsyncClient) -> None:
    resp = await db_client.post("/api/v1/items/nope--missing/vendor/verify/start")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_full_verify_and_respond_flow(
    db_client: AsyncClient, seed_item: SeededItem, monkeypatch: pytest.MonkeyPatch
) -> None:
    item, _scan = seed_item

    # 1. start → token
    start = await db_client.post(f"/api/v1/items/{item.slug}/vendor/verify/start")
    assert start.status_code == 200
    token = start.json()["token"]
    assert start.json()["file_path"] == ".saferskills/verify.txt"

    # 2. redeem — stub the GitHub raw fetch to return the committed token
    async def _fake_fetch(_item: object) -> str:
        return f"{token}\n"

    monkeypatch.setattr(vendor, "_fetch_verify_file", _fake_fetch)
    redeem = await db_client.post(
        f"/api/v1/items/{item.slug}/vendor/verify/redeem",
        json={"token": token, "github_user": "octocat"},
    )
    assert redeem.status_code == 200
    session_jwt = redeem.json()["session_jwt"]

    # 3. submit a response with the minted session
    submit = await db_client.post(
        f"/api/v1/items/{item.slug}/vendor/responses",
        headers=_bearer(session_jwt),
        json={"body_markdown": "Thanks — fixed in v2.", "trigger_rescan": False},
    )
    assert submit.status_code == 200
    body = submit.json()
    assert body["ok"] is True
    assert body["version"] == 1
    assert body["rescan_triggered"] is False

    # Security: public author attribution is the VERIFIED REPO, never the
    # self-asserted github_user — a repo-controller can't impersonate @anyone.
    detail = await db_client.get(f"/api/v1/items/{item.slug}")
    responses = detail.json()["vendor_responses"]
    assert len(responses) == 1
    assert responses[0]["author"] == f"{item.github_org}/{item.github_repo} maintainer"
    assert "octocat" not in responses[0]["author"]


@pytest.mark.asyncio
async def test_redeem_rejects_missing_token_in_file(
    db_client: AsyncClient, seed_item: SeededItem, monkeypatch: pytest.MonkeyPatch
) -> None:
    item, _scan = seed_item
    start = await db_client.post(f"/api/v1/items/{item.slug}/vendor/verify/start")
    token = start.json()["token"]

    async def _fake_fetch(_item: object) -> str:
        return "some-other-content\n"

    monkeypatch.setattr(vendor, "_fetch_verify_file", _fake_fetch)
    redeem = await db_client.post(
        f"/api/v1/items/{item.slug}/vendor/verify/redeem",
        json={"token": token, "github_user": "octocat"},
    )
    assert redeem.status_code == 400


@pytest.mark.asyncio
async def test_response_body_over_2000_chars_rejected(
    db_client: AsyncClient, seed_item: SeededItem
) -> None:
    item, _scan = seed_item
    token, _exp = vendor.mint_session_jwt(
        slug=item.slug, github_user="octocat", verification_id=uuid.uuid4()
    )
    resp = await db_client.post(
        f"/api/v1/items/{item.slug}/vendor/responses",
        headers=_bearer(token),
        json={"body_markdown": "x" * 2001, "trigger_rescan": False},
    )
    assert resp.status_code == 422
