"""Typed emit-helpers for the scan-engine + ingestion observability allowlists.

Locked decision D-30 + `.claude/rules/telemetry.md` § Event allowlist — scan
engine + D-04-22 ingestion events. This module is the ONLY sanctioned emission
path for scan-engine and ingestion events. Raw `posthog.capture()` /
`sentry_sdk.set_tag()` calls outside this module are a regression.

All property values are bucketed or closed-enum. No raw IPs, no emails, no
URLs, no `matched_content` strings. Bucket helpers are colocated below.

Phase A lands the helpers as no-op stubs (structlog-only). The PostHog +
OpenTelemetry adapters wire up in Phase B when the scan engine starts firing
real events.
"""

from __future__ import annotations

import hashlib
import re
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

# I-3.5 upload / visibility (D-UP-22). `artifact_source` is a SEPARATE property
# from `scan_submitted.source` (the trigger enum) — never overload the trigger.
type ArtifactSource = Literal["github", "upload"]
type Visibility = Literal["public", "unlisted"]
type UploadSizeBucket = Literal["<100KB", "100KB-1MB", "1-5MB", "5-10MB"]
type UploadRejectReason = Literal[
    "too_big", "bad_type", "binary", "archive_rejected", "rate_limited"
]

# I-04 ingestion events (D-04-22)
type IngestionItemsBucket = Literal["0", "1-10", "11-100", "101-1k", "1k+"]
type Ingestion304RatioBucket = Literal["0-25", "25-50", "50-75", "75-100"]
type IngestionFailureReason = Literal["rate_limit", "cf_challenge", "http_5xx", "timeout", "other"]
type CatalogItemArchivedReason = Literal["404_timeline", "maintainer_archived", "yanked"]


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


def upload_size_bucket(n: int) -> UploadSizeBucket:
    if n < 100_000:
        return "<100KB"
    if n < 1_000_000:
        return "100KB-1MB"
    if n < 5_000_000:
        return "1-5MB"
    return "5-10MB"


def ingestion_items_bucket(n: int) -> IngestionItemsBucket:
    """Bucket for items_added / items_updated in ingestion cycle events (D-04-22)."""
    if n == 0:
        return "0"
    if n <= 10:
        return "1-10"
    if n <= 100:
        return "11-100"
    if n <= 1000:
        return "101-1k"
    return "1k+"


def ingestion_304_ratio_bucket(ratio: float) -> Ingestion304RatioBucket:
    """Bucket a 304-hit ratio (0.0-1.0) into a percentage band (D-04-22)."""
    pct = ratio * 100
    if pct < 25:
        return "0-25"
    if pct < 50:
        return "25-50"
    if pct < 75:
        return "50-75"
    return "75-100"


# ─── Event emitters (1-14 per .claude/rules/telemetry.md) ─────────────────────


def _emit(event: str, **props: object) -> None:
    """Internal log shim. Phase B replaces this with PostHog + OTel dispatch."""
    logger.info(event, **props)


def emit_scan_submitted(
    *,
    source: ScanSource,
    idempotency_cache_hit: bool,
    artifact_source: ArtifactSource = "github",
    visibility: Visibility = "public",
    upload_size_bucket: UploadSizeBucket | None = None,
) -> None:
    """`source` stays the trigger enum (submission/ingestion/rescan_*); the I-3.5
    provenance lives in the SEPARATE `artifact_source` property (D-UP-22, P1-4).
    `upload_size_bucket` is set only for uploads."""
    props: dict[str, object] = {
        "source": source,
        "idempotency_cache_hit": idempotency_cache_hit,
        "artifact_source": artifact_source,
        "visibility": visibility,
    }
    if upload_size_bucket is not None:
        props["upload_size_bucket"] = upload_size_bucket
    _emit("scan_submitted", **props)


def emit_promote_to_public(*, catalog_item_id: object) -> None:
    """An unlisted run was promoted to public (D-UP-22)."""
    _emit("promote_to_public", catalog_item_id_bucket=hash_to_bucket(catalog_item_id))


def emit_upload_rejected(*, reason: UploadRejectReason, archive_sub: str | None = None) -> None:
    """An upload failed validation. `reason` is the bucketed cause; `archive_sub`
    carries the `archive_rejected:<sub>` detail (closed sub-set) when present.
    NEVER carries the token or any path/filename content."""
    props: dict[str, object] = {"reason": reason}
    if archive_sub is not None:
        props["archive_sub"] = archive_sub
    _emit("upload_rejected", **props)


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


# ─── Ingestion event emitters (D-04-22) ──────────────────────────────────────


def emit_ingestion_cycle_started(*, source: str, cadence: str) -> None:
    """`ingestion_cycle_started` — fired at the beginning of each adapter cycle.

    `source` is a closed-enum value from the 14-source YAML config (e.g.
    'github_skills', 'npm', 'mcp_so'). `cadence` is the cron string from the
    adapter's YAML (e.g. '0 * * * *'). Neither contains PII or raw URLs.
    """
    _emit("ingestion_cycle_started", source=source, cadence=cadence)


def emit_ingestion_cycle_completed(
    *,
    source: str,
    items_added: int,
    items_updated: int,
    duration_ms: int,
    http_304_ratio: float,
) -> None:
    """`ingestion_cycle_completed` — fired at the end of a successful adapter cycle.

    All numerics are bucketed before emission. `http_304_ratio` is a float in
    [0.0, 1.0] representing the fraction of requests served from Hishel cache
    (304-revalidation hits). No raw counts, no URLs, no item IDs.
    """
    _emit(
        "ingestion_cycle_completed",
        source=source,
        items_added_bucket=ingestion_items_bucket(items_added),
        items_updated_bucket=ingestion_items_bucket(items_updated),
        duration_ms_bucket=latency_bucket(duration_ms),
        http_304_ratio_bucket=ingestion_304_ratio_bucket(http_304_ratio),
    )


def emit_ingestion_cycle_failed(*, source: str, reason: IngestionFailureReason) -> None:
    """`ingestion_cycle_failed` — fired when an adapter cycle ends in a terminal error.

    `reason` is a closed enum; transient retries do NOT emit this event — only
    the final dead-letter failure does.
    """
    _emit("ingestion_cycle_failed", source=source, reason_enum=reason)


type ArchiveReason = Literal["404_timeline", "maintainer_archived", "yanked"]


def emit_ingestion_cycle_archived(*, source: str, reason: ArchiveReason) -> None:
    """`catalog_item_archived` (D-04-22 #20) — one per item flipped to archived.

    `source` is the trigger (e.g. 'archive_check'); `reason` is a closed enum.
    No item ID, no slug, no URL.
    """
    _emit("catalog_item_archived", source=source, reason_enum=reason)


def emit_popularity_recompute_completed(*, top500_changed_count: int) -> None:
    """`popularity_recompute_completed` (D-04-22 #21) — fired once per nightly
    recompute. The top-500 churn count is bucketed before emission (no raw count).
    """
    _emit(
        "popularity_recompute_completed",
        top500_changed_count_bucket=ingestion_items_bucket(top500_changed_count),
    )


# ─── Capability-token redaction (D-UP-32) ─────────────────────────────────────

_CAP_TOKEN_RE = re.compile(r"(/scans/r/)[^/?#\s]+")


def redact_capability_token(text: str) -> str:
    """Rewrite `/scans/r/<token>[...]` → `/scans/r/<redacted>` in any string.

    The capability token is possession-is-authorization — it must never land in
    an access log, an OTel span name, or a Sentry payload."""
    return _CAP_TOKEN_RE.sub(r"\1<redacted>", text)


def scrub_sentry_event(
    event: dict[str, object], _hint: dict[str, object] | None = None
) -> dict[str, object] | None:
    """Sentry `before_send` callback — redact the capability token from the event
    request URL + any breadcrumb URL (D-UP-32(b))."""
    request = event.get("request")
    if isinstance(request, dict):
        typed_req = cast(dict[str, object], request)
        url = typed_req.get("url")
        if isinstance(url, str):
            typed_req["url"] = redact_capability_token(url)
    breadcrumbs = event.get("breadcrumbs")
    values: list[object] = []
    if isinstance(breadcrumbs, dict):
        raw = cast(dict[str, object], breadcrumbs).get("values")
        if isinstance(raw, list):
            values = cast(list[object], raw)
    elif isinstance(breadcrumbs, list):
        values = cast(list[object], breadcrumbs)
    for crumb in values:
        if isinstance(crumb, dict):
            typed_crumb = cast(dict[str, object], crumb)
            for key in ("message", "data"):
                val = typed_crumb.get(key)
                if isinstance(val, str):
                    typed_crumb[key] = redact_capability_token(val)
    return event


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
