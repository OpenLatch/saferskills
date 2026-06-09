"""One-time run/submit token — mint, no-spend verify, single-use spend (I-5.5)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_scan import run_token as rt
from app.agent_scan.run_token import (
    RunTokenError,
    mint_submit_token,
    verify_run_token,
    verify_submit_token,
)

_RUN = "11111111-1111-1111-1111-111111111111"


def test_mint_then_no_spend_verify_ok() -> None:
    token = mint_submit_token(_RUN)
    verify_run_token(token, _RUN)  # no raise


def test_verify_rejects_wrong_run() -> None:
    token = mint_submit_token(_RUN)
    with pytest.raises(RunTokenError):
        verify_run_token(token, "22222222-2222-2222-2222-222222222222")


def test_verify_rejects_tampered_and_missing() -> None:
    token = mint_submit_token(_RUN)
    with pytest.raises(RunTokenError):
        verify_run_token(token + "x", _RUN)
    with pytest.raises(RunTokenError):
        verify_run_token(None, _RUN)


def test_verify_rejects_expired() -> None:
    # White-box: craft a token with a past expiry.
    payload = rt._payload_bytes(_RUN, exp=1)
    mac = rt._mac(rt._runtoken_key(), payload)
    token = f"{rt._b64url(payload)}.{mac}"
    with pytest.raises(RunTokenError):
        verify_run_token(token, _RUN)


@pytest.mark.asyncio
async def test_submit_token_is_single_use(db_session: AsyncSession) -> None:
    token = mint_submit_token(_RUN)
    await verify_submit_token(token, _RUN, db_session)  # first claim ok
    with pytest.raises(RunTokenError):
        await verify_submit_token(token, _RUN, db_session)  # replay → spent
