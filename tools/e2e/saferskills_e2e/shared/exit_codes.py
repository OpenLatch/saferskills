"""Process exit codes for the SaferSkills E2E orchestrator.

`all` propagates the first non-OK code it sees, so callers (CI, shell
pipelines) can branch on the specific failure mode without parsing
stdout.
"""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    """Stable wire contract — never renumber an existing value."""

    OK = 0
    FAIL_REACHABILITY = 10
    FAIL_HEALTH = 11
    FAIL_OPENAPI = 12
    FAIL_HOMEPAGE = 13
    FAIL_ITEM_DETAIL = 14
    FAIL_VENDOR_RESPOND = 15
    FAIL_BADGE = 16
    FAIL_OG = 17
    FAIL_UPLOAD_FLOW = 18
    FAIL_UNLISTED_FLOW = 19
    FAIL_CATALOG_BADGE = 21
    FAIL_CONFIG = 20
    FAIL_UNKNOWN = 99
