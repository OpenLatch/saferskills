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
| `catalog_*` | Catalog browse + filter + search |
| `artifact_*` | Artifact detail page interactions |
| `rule_*` | Rubric / methodology page interactions |
| `appeal_*` | Vendor-appeal form interactions (W5+ when the web form ships) |

### Property allowlist

Closed-enum + bucketed-numeric values only. **No PII, no source-content hashes in property values.**

- Closed enums: `artifact_kind` ∈ {`mcp`, `skill`, `rules`, `hooks`, `plugin`}; `severity` ∈ {`low`, `medium`, `high`, `critical`}; `rubric_version` (semver string).
- Bucketed numerics: score buckets `0-39 / 40-69 / 70-89 / 90-100`; counts bucketed to `0 / 1 / 2-5 / 6-20 / 21+`.
- Forbidden: raw URLs, raw repo names, raw user input, raw rule IDs in property values (the rule ID is the EVENT NAME via `rule_<id>`, not a property — closed enum).

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
| New PostHog property value allowed | "Property allowlist" — re-verify the bucketed-numeric / closed-enum invariant |
| Sentry sample rate / scope change | "Sentry" |
| New OTel exporter / endpoint | "OpenTelemetry" + `environment-config.md` |
| New vendor (e.g. a separate logs sink) | New section here + `environment-config.md` |
