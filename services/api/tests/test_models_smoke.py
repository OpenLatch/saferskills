"""Smoke test the 7-table scan surface — one round-trip insert per table.

Confirms the Phase A migration runs end-to-end and that all 7 tables accept
canonical-shape inserts. Does NOT exercise the SQLAlchemy generated models
(W1-stub-emitter still — Phase B replaces them); uses raw SQL via the session
connection so the test rides only on the migration's authoritative schema.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_catalog_item_round_trip(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            """
            INSERT INTO catalog_items (
                kind, slug, display_name, github_url, github_org, github_repo,
                default_branch, popularity_tier, popularity_score, sources
            ) VALUES (
                :kind, :slug, :name, :url, :org, :repo, :branch, :tier, :score,
                '[]'::jsonb
            )
            RETURNING id
            """
        ),
        {
            "kind": "mcp_server",
            "slug": "test-org--test-repo",
            "name": "test",
            "url": "https://github.com/test-org/test-repo",
            "org": "test-org",
            "repo": "test-repo",
            "branch": "main",
            "tier": "lite",
            "score": 50,
        },
    )
    item_id = result.scalar_one()
    assert item_id is not None


@pytest.mark.asyncio
async def test_scan_round_trip(db_session: AsyncSession) -> None:
    # Parent catalog item.
    item_id = (
        await db_session.execute(
            text(
                """
                INSERT INTO catalog_items (
                    kind, slug, display_name, github_org, github_repo,
                    default_branch, popularity_tier, popularity_score, sources
                ) VALUES (
                    'skill', 'org--scan-test', 'scan-test', 'org', 'scan-test',
                    'main', 'on_demand', 10, '[]'::jsonb
                )
                RETURNING id
                """
            )
        )
    ).scalar_one()

    scan_id = (
        await db_session.execute(
            text(
                """
                INSERT INTO scans (
                    catalog_item_id, idempotency_key, github_url, ref_sha,
                    aggregate_score, tier, sub_scores, score_breakdown,
                    rubric_version, engine_version, latency_ms, source
                ) VALUES (
                    :item_id, :idem, :url, :sha, 87, 'green',
                    '{"security":100,"supply_chain":85,"maintenance":100,"transparency":80,"community":100}'::jsonb,
                    '{}'::jsonb,
                    'a1b2c3d', 'def5678', 42000, 'submission'
                )
                RETURNING id
                """
            ),
            {
                "item_id": item_id,
                "idem": "a" * 64,
                "url": "https://github.com/org/scan-test",
                "sha": "f" * 40,
            },
        )
    ).scalar_one()
    assert scan_id is not None


@pytest.mark.asyncio
async def test_finding_round_trip(db_session: AsyncSession) -> None:
    # Catalog item + scan parent chain.
    item_id = (
        await db_session.execute(
            text(
                """
                INSERT INTO catalog_items (
                    kind, slug, display_name, github_org, github_repo,
                    default_branch, popularity_tier, popularity_score, sources
                ) VALUES (
                    'skill', 'org--finding-test', 'finding-test', 'org', 'finding-test',
                    'main', 'lite', 10, '[]'::jsonb
                )
                RETURNING id
                """
            )
        )
    ).scalar_one()
    scan_id = (
        await db_session.execute(
            text(
                """
                INSERT INTO scans (
                    catalog_item_id, idempotency_key, github_url, ref_sha,
                    aggregate_score, tier, sub_scores, score_breakdown,
                    rubric_version, engine_version, latency_ms, source
                ) VALUES (
                    :item_id, :idem, 'https://github.com/org/finding-test', :sha,
                    50, 'orange',
                    '{"security":50,"supply_chain":100,"maintenance":100,"transparency":100,"community":100}'::jsonb,
                    '{}'::jsonb,
                    'a1b2c3d', 'def5678', 30000, 'submission'
                )
                RETURNING id
                """
            ),
            {"item_id": item_id, "idem": "b" * 64, "sha": "e" * 40},
        )
    ).scalar_one()

    finding_id = (
        await db_session.execute(
            text(
                """
                INSERT INTO findings (
                    scan_id, rule_id, severity, sub_score, penalty,
                    status_at_scan, file_path, line_start,
                    matched_content_sha256, remediation_link, rubric_version
                ) VALUES (
                    :scan_id, 'SS-SKILL-INJECT-UNICODE-TAG-01', 'critical', 'security',
                    35, 'active', 'README.md', 42, :hash, 'https://example/r', 'a1b2c3d'
                )
                RETURNING id
                """
            ),
            {"scan_id": scan_id, "hash": "5" * 64},
        )
    ).scalar_one()
    assert finding_id is not None


@pytest.mark.asyncio
async def test_vendor_verification_round_trip(db_session: AsyncSession) -> None:
    item_id = (
        await db_session.execute(
            text(
                """
                INSERT INTO catalog_items (
                    kind, slug, display_name, github_org, github_repo,
                    default_branch, popularity_tier, popularity_score, sources
                ) VALUES (
                    'skill', 'org--verify-test', 'verify-test', 'org', 'verify-test',
                    'main', 'lite', 10, '[]'::jsonb
                )
                RETURNING id
                """
            )
        )
    ).scalar_one()
    now = datetime.now(UTC)
    ver_id = (
        await db_session.execute(
            text(
                """
                INSERT INTO vendor_verifications (
                    catalog_item_id, token_hash_sha256, issued_at, expires_at, state
                ) VALUES (:item_id, :hash, :issued, :expires, 'pending')
                RETURNING id
                """
            ),
            {
                "item_id": item_id,
                "hash": "c" * 64,
                "issued": now,
                "expires": now + timedelta(days=7),
            },
        )
    ).scalar_one()
    assert ver_id is not None


@pytest.mark.asyncio
async def test_vendor_response_round_trip(db_session: AsyncSession) -> None:
    item_id = (
        await db_session.execute(
            text(
                """
                INSERT INTO catalog_items (
                    kind, slug, display_name, github_org, github_repo,
                    default_branch, popularity_tier, popularity_score, sources
                ) VALUES (
                    'skill', 'org--resp-test', 'resp-test', 'org', 'resp-test',
                    'main', 'lite', 10, '[]'::jsonb
                )
                RETURNING id
                """
            )
        )
    ).scalar_one()
    now = datetime.now(UTC)
    ver_id = (
        await db_session.execute(
            text(
                """
                INSERT INTO vendor_verifications (
                    catalog_item_id, token_hash_sha256, issued_at, expires_at, state
                ) VALUES (:item_id, :hash, :issued, :expires, 'verified')
                RETURNING id
                """
            ),
            {
                "item_id": item_id,
                "hash": "d" * 64,
                "issued": now,
                "expires": now + timedelta(days=7),
            },
        )
    ).scalar_one()

    resp_id = (
        await db_session.execute(
            text(
                """
                INSERT INTO vendor_responses (
                    catalog_item_id, vendor_verification_id, body_markdown, version
                ) VALUES (:item_id, :ver_id, 'Test response body.', 1)
                RETURNING id
                """
            ),
            {"item_id": item_id, "ver_id": ver_id},
        )
    ).scalar_one()
    assert resp_id is not None


@pytest.mark.asyncio
async def test_item_source_round_trip(db_session: AsyncSession) -> None:
    item_id = (
        await db_session.execute(
            text(
                """
                INSERT INTO catalog_items (
                    kind, slug, display_name, github_org, github_repo,
                    default_branch, popularity_tier, popularity_score, sources
                ) VALUES (
                    'skill', 'org--src-test', 'src-test', 'org', 'src-test',
                    'main', 'lite', 10, '[]'::jsonb
                )
                RETURNING id
                """
            )
        )
    ).scalar_one()
    src_id = (
        await db_session.execute(
            text(
                """
                INSERT INTO item_sources (
                    catalog_item_id, registry_id, registry_url
                ) VALUES (:item_id, 'mcp_registry', 'https://example.test/listing')
                RETURNING id
                """
            ),
            {"item_id": item_id},
        )
    ).scalar_one()
    assert src_id is not None


@pytest.mark.asyncio
async def test_rate_limit_round_trip(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    await db_session.execute(
        text(
            """
            INSERT INTO rate_limits (ip_hash, bucket, window_start, count)
            VALUES (:ip, 'scan_submit', :start, 1)
            """
        ),
        {"ip": "f" * 64, "start": now},
    )
    count = (
        await db_session.execute(
            text(
                """
                SELECT count FROM rate_limits
                WHERE ip_hash = :ip AND bucket = 'scan_submit'
                """
            ),
            {"ip": "f" * 64},
        )
    ).scalar_one()
    assert count == 1
