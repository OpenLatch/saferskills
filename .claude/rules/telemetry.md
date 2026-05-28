---
paths:
  - "services/api/app/**"
  - "webapp/src/**"
  - "ui/**"
---

# Telemetry

> **Paths**: `services/api/app/**`, `webapp/src/**`, `ui/**`

## Purpose

Telemetry has three independent legs at W1:

1. **PostHog** — product analytics (client-side, opt-in via cookie banner W5+; W1 fires only privacy-safe events).
2. **Sentry** — errors only (no breadcrumbs containing scanned-artifact content).
3. **OpenTelemetry** — server-side traces + metrics (OTLP exporter to a SaferSkills-owned collector).

All three projects are **SaferSkills-specific and separate from any OpenLatch projects** (per the brand-independence locked-decision D-19). This protects independent voice: a SaferSkills outage never bleeds into OpenLatch dashboards, and SaferSkills product usage never feeds OpenLatch analytics.

## PostHog (client-side)

Initialized in the webapp via `PUBLIC_POSTHOG_KEY` (cf. `environment-config.md`). At W1 the page is anonymous; PostHog identification arrives with auth in W5.

### Closed-enum event names

Every event name lives in `webapp/src/lib/analytics.ts::events` — adding an event = adding an entry there. The runtime enforces the closed set; an arbitrary string fails type-check.

| Event prefix | When it fires |
|---|---|
| `homepage_*` | Homepage CTA + hero clicks |
| `catalog_*` | Catalog browse + filter + search — landed Phase B |
| `scan_report_*` | Scan-report page interactions (sub-score accordion expand, install command copy, embed badge copy) — landed Phase B |
| `item_detail_*` | Item-detail page interactions (chart hover/click) — lands Phase C |
| `artifact_*` | Artifact detail page interactions |
| `rule_*` | Rubric / methodology page interactions |
| `appeal_*` | Vendor-appeal form interactions (W5+ when the web form ships) |

### Property allowlist

Closed-enum + bucketed-numeric values only. **No PII, no source-content hashes in property values.**

- Closed enums: `artifact_kind` ∈ {`mcp`, `skill`, `rules`, `hooks`, `plugin`}; `severity` ∈ {`info`, `low`, `medium`, `high`, `critical`} (5-tier per locked decision D-02); `sub_score` ∈ {`security`, `supply_chain`, `maintenance`, `transparency`, `community`} (5-axis per D-01); `rubric_version` (git SHA string).
- Bucketed numerics: score buckets `0-39 / 40-69 / 70-89 / 90-100`; counts bucketed to `0 / 1 / 2-5 / 6-20 / 21+`; latency_ms bucketed to `<10 / <60 / <300 / >=300`; backoff_seconds bucketed identically; installation_id hashed via `hash%16`.
- Forbidden: raw URLs, raw repo names, raw user input in property values. **`rule_id` IS a permitted closed-enum property value** for `rule_*` events (the enum is the active rubric — bounded set), per the scan-engine event allowlist below.

## Event allowlist — scan engine (W2+)

The scan engine emits a closed enum of 14 events (per locked decision D-30). The list is exhaustive — adding a new event is a `.claude/rules/telemetry.md` PR + an `app/observability/events.py` typed-helper PR. The helpers under `services/api/app/observability/events.py` are the only sanctioned emission path; raw `posthog.capture()` / `sentry_sdk.set_tag()` calls outside that module are a regression.

| # | Event | Properties (all bucketed / closed-enum) |
|---|---|---|
| 1 | `scan_submitted` | `source` ∈ {`submission`, `ingestion`, `rescan_drift`, `rescan_appeal`}; `idempotency_cache_hit` (bool) |
| 2 | `scan_started` | `scan_id_bucket` (hash%16) |
| 3 | `scan_completed` | `scan_id_bucket`; `tier` ∈ {`green`,`yellow`,`orange`,`red`,`unscoped`}; `latency_ms_bucket`; `findings_count_bucket` |
| 4 | `scan_failed` | `scan_id_bucket`; `failure_class` ∈ {`fetch_timeout`,`tar_oversize`,`rule_panic`,`unknown`} |
| 5 | `scan_timeout` | `scan_id_bucket`; `stage` ∈ {`fetch`,`extract`,`detect`,`aggregate`} |
| 6 | `rule_fired` | `rule_id` (closed enum = active rubric); `severity`; `sub_score`; `status_at_scan` ∈ {`shadow`,`active`} |
| 7 | `rule_skipped_timeout` | `rule_id` |
| 8 | `rule_shadow_promoted` | `rule_id`; `fp_rate_bucket` ∈ {`0`,`<5%`,`5-10%`,`>10%`} |
| 9 | `rule_shadow_demoted` | `rule_id`; `fp_rate_bucket` |
| 10 | `github_rate_limit_hit` | `resource` ∈ {`core`,`search`,`code_search`,`integration_manifest`}; `kind` ∈ {`primary`,`secondary`}; `retry_attempt`; `backoff_seconds_bucket` |
| 11 | `github_rate_limit_recovered` | `resource` |
| 12 | `vendor_verification_succeeded` | `catalog_item_id_bucket` (hash%16) |
| 13 | `vendor_response_submitted` | `catalog_item_id_bucket`; `body_length_bucket` ∈ {`<500`,`500-1000`,`1000-2000`} |
| 14 | `rescan_triggered_drift` | `catalog_item_id_bucket`; `hash_delta_files_count_bucket` ∈ {`1`,`2-5`,`6-20`,`21+`} |

No raw IPs, no emails, no URLs, no `matched_content` strings. Bucketing helpers (`hash_to_bucket`, `latency_bucket`, `count_bucket`) live alongside the emit-helpers in `services/api/app/observability/events.py`.

## Sentry

`SENTRY_DSN` env var (cf. `environment-config.md`); separate Sentry project from OpenLatch.

- **Errors only.** No transactions, no performance traces, no session replay at W1.
- **Breadcrumb scrubbing**: the Sentry init MUST configure `beforeBreadcrumb` to drop any breadcrumb whose `data` field references a path under `rubric/`, `schemas/`, or any user-submitted URL. This prevents scanned-artifact content leaking into Sentry.
- **PII scrubbing**: `sendDefaultPii: false`. Email scrubbing on every event payload.
- **Single channel**: all alerts land in one Slack/Discord channel; the env tag (`development` / `staging` / `production`) is in the message body, never used as the channel router.
- Sample rate: 100% of errors in W1 (low volume); revisit when traffic grows.

## OpenTelemetry

`OTEL_EXPORTER_OTLP_ENDPOINT` (optional; cf. `environment-config.md`). Server-side only at W1.

- Traces: every FastAPI route emits a span; scan-pipeline invocations emit child spans per rule fired.
- Metrics: standard process + HTTP histograms; per-rule firing counters (`rule_id` as a low-cardinality label).
- **Never log raw scanned-artifact bytes** in span attributes. Hashes + sizes + counts only.

## Hard rules

1. **No PII anywhere.** PostHog property values, Sentry breadcrumbs, OTel span attributes — all three legs treat user input as untrusted and scrub it.
2. **Closed-enum event names + property values.** Adding an event = a `webapp/src/lib/analytics.ts` entry change reviewed in the PR.
3. **Bucketed numerics, never raw counts** in PostHog property values.
4. **Separate vendor projects** for PostHog + Sentry + OTel — never share a project / DSN / endpoint with another product.
5. **Brand-independence**: when documentation or dashboards reference "the SaferSkills team", they reference SaferSkills maintainers only — never label cross-product dashboards.

## When to update this rule

| Change | Updates here |
|---|---|
| New event prefix added | "Closed-enum event names" table + `webapp/src/lib/analytics.ts` |
| New scan-engine event | "Event allowlist — scan engine" table + `services/api/app/observability/events.py` typed helper |
| New PostHog property value allowed | "Property allowlist" — re-verify the bucketed-numeric / closed-enum invariant |
| Sentry sample rate / scope change | "Sentry" |
| New OTel exporter / endpoint | "OpenTelemetry" + `environment-config.md` |
| New vendor (e.g. a separate logs sink) | New section here + `environment-config.md` |
