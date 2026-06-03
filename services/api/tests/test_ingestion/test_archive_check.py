"""archive_check timeline (D-04-17) — boundary cases at 3 / 6 / 7 consecutive 404s."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.tasks_archive import run_archive_check

from ._catalog_factory import make_item


@pytest.mark.asyncio
async def test_boundaries_flip_correctly(db_session: AsyncSession) -> None:
    healthy = make_item(consecutive404_count=0, availability="available")
    just_under = make_item(consecutive404_count=2, availability="available")
    unavailable_3 = make_item(consecutive404_count=3, availability="available")
    unavailable_6 = make_item(consecutive404_count=6, availability="available")
    archived_7 = make_item(consecutive404_count=7, availability="available")
    db_session.add_all([healthy, just_under, unavailable_3, unavailable_6, archived_7])
    await db_session.commit()

    result = await run_archive_check(db_session)
    assert result["archived"] >= 1
    assert result["unavailable"] >= 2

    for item in (healthy, just_under, unavailable_3, unavailable_6, archived_7):
        await db_session.refresh(item)

    assert healthy.availability == "available"
    assert just_under.availability == "available"  # < 3 → untouched
    assert unavailable_3.availability == "unavailable"
    assert unavailable_6.availability == "unavailable"
    assert archived_7.availability == "archived"
    assert archived_7.archived is True


@pytest.mark.asyncio
async def test_recovered_flips_back(db_session: AsyncSession) -> None:
    recovered = make_item(consecutive404_count=0, availability="unavailable", archived=False)
    db_session.add(recovered)
    await db_session.commit()
    result = await run_archive_check(db_session)
    assert result["recovered"] >= 1
    await db_session.refresh(recovered)
    assert recovered.availability == "available"


@pytest.mark.asyncio
async def test_upload_rows_untouched(db_session: AsyncSession) -> None:
    upload = make_item(
        consecutive404_count=9, source_kind="upload", github_url=None, availability="available"
    )
    db_session.add(upload)
    await db_session.commit()
    await run_archive_check(db_session)
    await db_session.refresh(upload)
    assert upload.availability == "available"  # never archived (not public-github)
