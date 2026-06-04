"""Tests for GET /api/v1/rubric/content (D-05-32).

The endpoint serves the generated explainable-finding prose map the install CLI
caches offline. No DB — the payload is loaded from `app/generated/rule_content.json`.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_rubric_content_shape(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/rubric/content")
    assert resp.status_code == 200
    assert "public" in resp.headers.get("cache-control", "")

    body = resp.json()
    assert "rubric_version" in body
    assert isinstance(body["rubric_version"], str) and body["rubric_version"]
    assert isinstance(body["rules"], dict)
    assert body["rules"], "expected at least one rule in the content map"

    # Every entry carries the explainable-finding prose fields, snake_case.
    rule_id, entry = next(iter(body["rules"].items()))
    assert entry["rule_id"] == rule_id
    for key in ("title", "explanation", "severity", "sub_score", "category_label"):
        assert key in entry, key
    assert "action" in entry["remediation"]
