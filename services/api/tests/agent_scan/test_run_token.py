"""One-time run/submit token — mint, no-spend verify, single-use spend."""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo

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


class _FixedClock:
    """Stand-in for the `datetime` the run_token module reads — pins `now()` so an
    already-minted token reads as expired without crafting one via private helpers."""

    def __init__(self, when: datetime) -> None:
        self._when = when

    def now(self, tz: tzinfo | None = None) -> datetime:
        return self._when


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


def test_verify_rejects_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    token = mint_submit_token(_RUN)
    # Advance the verifier's clock past the token's TTL → expired.
    monkeypatch.setattr(rt, "datetime", _FixedClock(datetime(2999, 1, 1, tzinfo=UTC)))
    with pytest.raises(RunTokenError):
        verify_run_token(token, _RUN)


@pytest.mark.asyncio
async def test_submit_token_is_single_use(db_session: AsyncSession) -> None:
    token = mint_submit_token(_RUN)
    await verify_submit_token(token, _RUN, db_session)  # first claim ok
    with pytest.raises(RunTokenError):
        await verify_submit_token(token, _RUN, db_session)  # replay → spent
