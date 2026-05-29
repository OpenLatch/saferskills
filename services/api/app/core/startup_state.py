"""Startup state — tracks whether critical startup steps completed successfully.

Other modules import and check this singleton to decide whether the API should
serve traffic or return 503. Trimmed from openlatch-platform's equivalent:
SaferSkills' only startup-critical step is migrations (no bootstrap/seed/
partition stages — those don't exist in single-tenant, auth-less SaferSkills).
"""

import structlog

logger = structlog.get_logger(__name__)


class _StartupState:
    """Singleton tracking startup health."""

    def __init__(self) -> None:
        self.migrations_ok: bool = False
        self.migrations_error: str | None = None

    @property
    def is_healthy(self) -> bool:
        return self.migrations_ok

    def mark_migrations_ok(self) -> None:
        self.migrations_ok = True
        self.migrations_error = None

    def mark_migrations_failed(self, error: str) -> None:
        self.migrations_ok = False
        self.migrations_error = error
        logger.warning("startup_state_degraded", reason="migrations_failed", error=error)


startup_state = _StartupState()
