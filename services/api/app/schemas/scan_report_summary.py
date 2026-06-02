"""Hand-written `ScanReportSummary` response model.

The generated `app/schemas/generated/scan_report_summary.py` inherits from
plain `BaseModel` with strict `extra='forbid'` config — fine as an entity
shape, but not suitable as a FastAPI `response_model` for ORM rows.

This wrapper:
- Inherits `OrmBaseModel` so `from_attributes=True` + `populate_by_name=True`
  are on (lets us pass SQLAlchemy rows directly).
- Mirrors the generated field set so the wire shape is identical.
- Stays the only Pydantic class FastAPI sees on the response side; the
  generator is the source of truth for the *shape*, this is the source of
  truth for the *FastAPI runtime*.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.orm_base import OrmBaseModel

ScanTier = Literal["green", "yellow", "orange", "red", "unscoped"]


class ScanReportSummary(OrmBaseModel):
    id: str = Field(..., description="Scan UUID rendered as string.")
    github_url: str | None = None
    slug: str
    aggregate_score: int = Field(..., ge=0, le=100)
    tier: ScanTier
    scanned_at: datetime
    findings_count: int = Field(default=0, ge=0)
    author: str | None = None
    title: str | None = None


class ListEnvelope(OrmBaseModel):
    data: list[ScanReportSummary]
    next_cursor: str | None = Field(default=None)
    total_count: int = Field(default=0, ge=0)
