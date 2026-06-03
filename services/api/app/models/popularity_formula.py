"""SQLAlchemy ORM for `popularity_formulas` (internal — no JSON-Schema source).

Version-locked popularity weights (D-04-13). Seeded with `popularity_v1` by
migration 0011. Consumed by the Phase C popularity_recompute task; changing
weights = a new version row + a recompute, never an in-place edit.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PopularityFormula(Base):
    __tablename__ = "popularity_formulas"

    version: Mapped[str] = mapped_column(String(20), primary_key=True)
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
