"""add cli_pow_spent (single-use CLI Proof-of-Work challenge store)

Revision ID: 0016_cli_pow_spent
Revises: 0015_install_events
Create Date: 2026-06-04

I-05 Install CLI (D-05-30). The CLI can't solve a Turnstile CAPTCHA, so a stateless
HMAC-signed Proof-of-Work challenge replaces Turnstile on CLI scan-submit. This
migration adds:

- `cli_pow_spent` — a single-use ledger keyed by `challenge_sha256`. A solved
  challenge is INSERTed once; a replay collides on the PK and is rejected. Swept by
  `app/core/sweeps.py::sweep_cli_pow` once `expires_at` passes.
- `chk_rate_limits_bucket` gains the `cli_scan_submit` bucket (the PoW-path per-IP
  cap, distinct from the Turnstile `scan_submit` bucket). VARCHAR + CHECK (the
  `rate_limits` table is an internal hand-written store, not a native-enum column).

Internal hand-written store (no JSON-Schema source, no wire DTO) — mirrors
`install_events`. Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_cli_pow_spent"
down_revision: str | None = "0015_install_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# `rate_limits.bucket` CHECK lineage: 0001 -> 0006 (+artifact_download) ->
# 0008 (+private_lookup) -> here (+cli_scan_submit).
_OLD_BUCKETS = (
    "scan_submit",
    "scan_read",
    "item_read",
    "item_list",
    "artifact_download",
    "private_lookup",
)
_NEW_BUCKETS = (*_OLD_BUCKETS, "cli_scan_submit")


def _quoted(values: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _bucket_check(values: Sequence[str]) -> str:
    return f"bucket IN ({_quoted(values)})"


def upgrade() -> None:
    op.create_table(
        "cli_pow_spent",
        sa.Column("challenge_sha256", sa.String(64), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_cli_pow_spent_expires_at", "cli_pow_spent", ["expires_at"])

    # rate_limits CHECK += cli_scan_submit (drop + recreate).
    op.drop_constraint("chk_rate_limits_bucket", "rate_limits", type_="check")
    op.create_check_constraint("chk_rate_limits_bucket", "rate_limits", _bucket_check(_NEW_BUCKETS))


def downgrade() -> None:
    op.drop_constraint("chk_rate_limits_bucket", "rate_limits", type_="check")
    op.create_check_constraint("chk_rate_limits_bucket", "rate_limits", _bucket_check(_OLD_BUCKETS))

    op.drop_index("idx_cli_pow_spent_expires_at", table_name="cli_pow_spent")
    op.drop_table("cli_pow_spent")
