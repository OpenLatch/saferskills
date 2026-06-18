"""SQLAlchemy ORM for `cli_pow_spent` (internal — no JSON-Schema source).

A single-use ledger for the stateless CLI Proof-of-Work gate. The
challenge itself is stateless (HMAC-signed, no server storage), so the only thing
to persist is "this exact solved challenge has already been spent" — keyed by the
sha256 of the challenge string. A solved challenge is INSERTed once; a replay
collides on the PK (`IntegrityError`) and is rejected. Swept after `expires_at` by
`app/core/sweeps.py::sweep_cli_pow`.

Internal storage only — NOT part of the generated entity pipeline (no
`schemas/*.schema.json`, no Pydantic/Zod/TS DTO, never serialized). Hand-written,
registered in `app/models/__init__.py`; mirrors `install_event`.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CliPowSpent(Base):
    __tablename__ = "cli_pow_spent"

    # sha256 of the full challenge string (the `b64url(payload).hex(hmac)` form).
    challenge_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
