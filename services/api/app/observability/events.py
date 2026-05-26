"""Typed emit-helpers for the 14-event scan-engine observability allowlist.

Locked decision D-30 + `.claude/rules/telemetry.md` § Event allowlist — scan
engine. This module is the ONLY sanctioned emission path for scan-engine
events. Raw `posthog.capture()` / `sentry_sdk.set_tag()` calls outside this
module are a regression.

All property values are bucketed or closed-enum. No raw IPs, no emails, no
URLs, no `matched_content` strings. Bucket helpers are colocated below.

Phase A lands the helpers as no-op stubs (structlog-only). The PostHog +
OpenTelemetry adapters wire up in Phase B when the scan engine starts firing
real events.
"""

from __future__ import annotations

import hashlib
from typing import Literal, cast

import structlog

logger = structlog.get_logger("saferskills.observability")

# ─── Closed-enum types (PEP 695 syntax — Python 3.12+) ───────────────────────

type ScanSource = Literal["submission", "ingestion", "rescan_drift", "rescan_appeal"]
type ScanStage = Literal["fetch", "extract", "detect", "aggregate"]
type FailureClass = Literal["fetch_timeout", "tar_oversize", "rule_panic", "unknown"]
type Severity = Literal["info", "low", "medium", "high", "critical"]
type SubScore = Literal["security", "supply_chain", "maintenance", "transparency", "community"]
type StatusAtScan = Literal["shadow", "active"]
type TierBucket = Literal["green", "yellow", "orange", "red", "unscoped"]
type GitHubResource = Literal["core", "search", "code_search", "integration_manifest"]
type GitHubRateLimitKind = Literal["primary", "secondary"]

type LatencyBucket = Literal["<10", "<60", "<300", ">=300"]
type BackoffSecondsBucket = Literal["<10", "<60", "<300", ">=300"]
type CountBucket = Literal["0", "1", "2-5", "6-20", "21+"]
type HashDeltaBucket = Literal["1", "2-5", "6-20", "21+"]
type BodyLengthBucket = Literal["<500", "500-1000", "1000-2000"]
type FpRateBucket = Literal["0", "<5%", "5-10%", ">10%"]


# ─── Bucket helpers ───────────────────────────────────────────────────────────


def hash_to_bucket(identifier: object, num_buckets: int = 16) -> int:
    """Stable bucket assignment: `hash(identifier) % num_buckets`.

    Use for `scan_id_bucket` / `catalog_item_id_bucket` / `installation_id_bucket`.
    SHA-256 of the str() form so the bucket survives across Python invocations.
    """
    digest = hashlib.sha256(str(identifier).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % num_buckets


def latency_bucket(ms: int) -> LatencyBucket:
    if ms < 10:
        return "<10"
    if ms < 60:
        return "<60"
    if ms < 300:
        return "<300"
    return ">=300"


def backoff_bucket(seconds: int) -> BackoffSecondsBucket:
    if seconds < 10:
        return "<10"
    if seconds < 60:
        return "<60"
    if seconds < 300:
        return "<300"
    return ">=300"


def count_bucket(n: int) -> CountBucket:
    if n == 0:
        return "0"
    if n == 1:
        return "1"
    if n <= 5:
        return "2-5"
    if n <= 20:
        return "6-20"
    return "21+"


def hash_delta_bucket(n: int) -> HashDeltaBucket:
    if n <= 1:
        return "1"
    if n <= 5:
        return "2-5"
    if n <= 20:
        return "6-20"
    return "21+"


def body_length_bucket(length: int) -> BodyLengthBucket:
    if length < 500:
        return "<500"
    if length < 1000:
        return "500-1000"
    return "1000-2000"


def fp_rate_bucket(rate: float) -> FpRateBucket:
    if rate == 0:
        return "0"
    if rate < 0.05:
        return "<5%"
    if rate <= 0.10:
        return "5-10%"
    return ">10%"


# ─── Event emitters (1-14 per .claude/rules/telemetry.md) ─────────────────────


def _emit(event: str, **props: object) -> None:
    """Internal log shim. Phase B replaces this with PostHog + OTel dispatch."""
    logger.info(event, **props)


def emit_scan_submitted(*, source: ScanSource, idempotency_cache_hit: bool) -> None:
    _emit("scan_submitted", source=source, idempotency_cache_hit=idempotency_cache_hit)


def emit_scan_started(*, scan_id: object) -> None:
    _emit("scan_started", scan_id_bucket=hash_to_bucket(scan_id))


def emit_scan_completed(
    *,
    scan_id: object,
    tier: TierBucket,
    latency_ms: int,
    findings_count: int,
) -> None:
    _emit(
        "scan_completed",
        scan_id_bucket=hash_to_bucket(scan_id),
        tier=tier,
        latency_ms_bucket=latency_bucket(latency_ms),
        findings_count_bucket=count_bucket(findings_count),
    )


def emit_scan_failed(*, scan_id: object, failure_class: FailureClass) -> None:
    _emit("scan_failed", scan_id_bucket=hash_to_bucket(scan_id), failure_class=failure_class)


def emit_scan_timeout(*, scan_id: object, stage: ScanStage) -> None:
    _emit("scan_timeout", scan_id_bucket=hash_to_bucket(scan_id), stage=stage)


def emit_rule_fired(
    *,
    rule_id: str,
    severity: Severity,
    sub_score: SubScore,
    status_at_scan: StatusAtScan,
) -> None:
    _emit(
        "rule_fired",
        rule_id=rule_id,
        severity=severity,
        sub_score=sub_score,
        status_at_scan=status_at_scan,
    )


def emit_rule_skipped_timeout(*, rule_id: str) -> None:
    _emit("rule_skipped_timeout", rule_id=rule_id)


def emit_rule_shadow_promoted(*, rule_id: str, fp_rate: float) -> None:
    _emit("rule_shadow_promoted", rule_id=rule_id, fp_rate_bucket=fp_rate_bucket(fp_rate))


def emit_rule_shadow_demoted(*, rule_id: str, fp_rate: float) -> None:
    _emit("rule_shadow_demoted", rule_id=rule_id, fp_rate_bucket=fp_rate_bucket(fp_rate))


def emit_github_rate_limit_hit(
    *,
    resource: GitHubResource,
    kind: GitHubRateLimitKind,
    retry_attempt: int,
    backoff_seconds: int,
) -> None:
    _emit(
        "github_rate_limit_hit",
        resource=resource,
        kind=kind,
        retry_attempt=retry_attempt,
        backoff_seconds_bucket=backoff_bucket(backoff_seconds),
    )


def emit_github_rate_limit_recovered(*, resource: GitHubResource) -> None:
    _emit("github_rate_limit_recovered", resource=resource)


def emit_vendor_verification_succeeded(*, catalog_item_id: object) -> None:
    _emit("vendor_verification_succeeded", catalog_item_id_bucket=hash_to_bucket(catalog_item_id))


def emit_vendor_response_submitted(*, catalog_item_id: object, body_length: int) -> None:
    _emit(
        "vendor_response_submitted",
        catalog_item_id_bucket=hash_to_bucket(catalog_item_id),
        body_length_bucket=body_length_bucket(body_length),
    )


def emit_rescan_triggered_drift(*, catalog_item_id: object, hash_delta_files_count: int) -> None:
    _emit(
        "rescan_triggered_drift",
        catalog_item_id_bucket=hash_to_bucket(catalog_item_id),
        hash_delta_files_count_bucket=hash_delta_bucket(hash_delta_files_count),
    )


# ─── Sentry breadcrumb scrubber ───────────────────────────────────────────────

_SCRUBBED_PATH_PREFIXES = ("rubric/", "schemas/", "tools/fp-audit/fixtures/")
_SCRUBBED_URL_FRAGMENTS = ("github.com/", "raw.githubusercontent.com/", "codeload.github.com/")


def scrub_sentry_breadcrumb(
    crumb: dict[str, object], _hint: dict[str, object] | None = None
) -> dict[str, object] | None:
    """Sentry `before_breadcrumb` callback. Drop any breadcrumb whose data
    references a path under rubric/, schemas/, tools/fp-audit/fixtures/, or
    any GitHub URL — these may contain scanned-artifact bytes or vendor names
    we should not leak to Sentry. Returning None drops the breadcrumb.
    """
    data = crumb.get("data")
    if isinstance(data, dict):
        typed_data = cast(dict[object, object], data)
        for value in typed_data.values():
            if not isinstance(value, str):
                continue
            if any(value.startswith(p) or f"/{p}" in value for p in _SCRUBBED_PATH_PREFIXES):
                return None
            lowered = value.lower()
            if any(frag in lowered for frag in _SCRUBBED_URL_FRAGMENTS):
                return None
    message = crumb.get("message")
    if isinstance(message, str):
        lowered = message.lower()
        if any(frag in lowered for frag in _SCRUBBED_URL_FRAGMENTS):
            return None
    return crumb
