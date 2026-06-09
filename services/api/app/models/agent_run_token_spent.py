"""AgentRunTokenSpent — single-use ledger for the one-time agent submit token.

Hand-written internal store (no JSON-Schema source, no wire DTO). Mirrors
`cli_pow_spent` EXACTLY: a minted submit token is claimed once via
`INSERT ... ON CONFLICT DO NOTHING`; a replay collides on the PK and is rejected
(403, silent). Keyed by `token_sha256` — there is NO `run_id` FK, so it is reaped
purely by expiry (`app/core/sweeps.py::sweep_agent_run_tokens`), never by the run
cascade. See `.claude/rules/database.md` § Agent scan + `security.md` D-5.5-11.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AgentRunTokenSpent(Base):
    __tablename__ = "agent_run_token_spent"

    token_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:
        return f"AgentRunTokenSpent(token_sha256={self.token_sha256!r})"
