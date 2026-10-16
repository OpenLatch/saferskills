---
paths:
  - "services/api/app/observability/**"
  - "services/api/app/core/observability.py"
  - "services/api/app/core/feature_flags.py"
  - "webapp/src/lib/analytics.ts"
  - "webapp/src/lib/observability.ts"
  - "webapp/src/lib/feature-flags.ts"
  - "webapp/src/middleware.ts"
  - "cli/src/core/telemetry.rs"
---

# Telemetry

> **Paths**: the telemetry-authoring surfaces only — `app/observability/**` + `app/core/{observability,feature_flags}.py` (backend), `webapp/src/lib/{analytics,observability,feature-flags}.ts` + `webapp/src/middleware.ts` (webapp SSR errors), `cli/src/core/telemetry.rs`. (Emission is centralized — `app/observability/events.py` is the only sanctioned backend emit path and `webapp/src/lib/analytics.ts` the only event registry — so scoping to those files catches every event change without loading on unrelated app edits.)

## Purpose

Telemetry has two independent destinations:

1. **PostHog** — privacy-safe product analytics and error tracking in the dedicated EU **SaferSkills (all env)** project **272364**. Browser, SSR, API, worker and CLI share this project; environment and service properties distinguish events.
2. **OpenTelemetry / Grafana** — existing server-side traces, logs and metrics. Error tracking changes do not replace these exporters.

## PostHog (client-side)

Initialized in the webapp via `PUBLIC_POSTHOG_KEY` (cf. `environment-config.md`). The page is anonymous for now; PostHog identification arrives with auth.

**Common metadata.** Every event carries `product: "saferskills"`. Error events also identify their `service`, `environment`, and `release`. No personal identification or cross-product identity stitching is permitted.

**Routing.** The browser uses the same-origin `/ingest` proxy to fixed EU upstreams. Server/CLI ingestion uses `https://eu.i.posthog.com`; the dashboard and upload CLI use `https://eu.posthog.com`. `POSTHOG_PROJECT_KEY` is the public ingestion key, distinct from the private upload variable `POSTHOG_CLI_API_KEY` (mapped from staging GitHub secret `POSTHOG_SERVER_KEY`) used only for CI uploads.

### Closed-enum event names

Every event name lives in `webapp/src/lib/analytics.ts::events` — adding an event = adding an entry there. The runtime enforces the closed set; an arbitrary string fails type-check.

| Event prefix | When it fires |
|---|---|
| `homepage_*` | Homepage CTA + hero clicks; the dual-mode scan submit (`homepage_scan_submitted`) + the homepage audit-panel affordance (`homepage_scan_panel_started`). |
| `catalog_*` | Catalog browse + filter + search. |
| `scan_report_*` | Scan-report page interactions (sub-score accordion expand, install command copy — incl. the `zip` download-bytes button on upload reports, embed badge copy, **capability type-filter + capability-row expand** on the repo scan report, **file-tab select** (`scan_report_file_selected`) on a multi-file upload report, **finding-card expand** (`scan_report_finding_expanded` `{rule_id}`) on every report surface). |
| `item_detail_*` | Item-detail page interactions (chart hover/click). |
| `unlisted_*` | Unlisted (capability-URL) manage-bar actions — `unlisted_manage_action` `{action: copy_link\|promote\|delete}`. **Never** carries the `share_token`, slug, filename, or any path content. |
| `artifact_*` | Artifact detail page interactions |
| `rule_*` | Rubric / methodology page interactions — incl. the methodology CSV export (`rule_csv_exported` `{count_bucket}`, the visible-rule count bucketed `0`/`1`/`2-5`/`6-20`/`21+`; never a rule_id list) and the `/methodology` mode control (`rule_methodology_tab_selected` `{tab: capability\|agent}` — closed enum, fired on Capability rules ↔ Agent pack switch) |
| `agent_report_*` | Agent Report (`/agents/*`) interactions — `agent_report_tab_selected` `{tab: report\|findings\|component}`, `agent_report_shared`, `agent_report_exported`, `agent_report_reply_submitted` (the last three carry **no** properties). **Never** the `share_token`, agent name, runtime, or any transcript/finding content. |
| `agent_scan_*` (frontend) | Agent-scan activation surfaces — `agent_scan_prompt_minted` `{surface: homepage\|scan\|picker, visibility: public\|unlisted}` fires once per successful bootstrap mint+copy (homepage card 02 / `/scan` agent pane / platform picker). Both properties closed enums. **Never** the `run_id`, the one-time `submit_token`/run token, or any prompt content. (Distinct from the backend `agent_scan_completed`, event #24 below.) |
| `appeal_*` | Vendor-appeal form interactions (when the web form ships with auth) |

### Property allowlist

Closed-enum + bucketed-numeric values only. **No PII, no source-content hashes in property values.**

- Closed enums: `artifact_kind` ∈ {`mcp`, `skill`, `rules`, `hooks`, `plugin`}; `severity` ∈ {`info`, `low`, `medium`, `high`, `critical`} (5-tier); `sub_score` ∈ {`security`, `supply_chain`, `maintenance`, `transparency`, `community`} (5-axis); `rubric_version` (git SHA string).
- Bucketed numerics: score buckets `0-39 / 40-69 / 70-89 / 90-100`; counts bucketed to `0 / 1 / 2-5 / 6-20 / 21+`; latency_ms bucketed to `<10 / <60 / <300 / >=300`; backoff_seconds bucketed identically; installation_id hashed via `hash%16`.
- Forbidden: raw URLs, raw repo names, raw user input in property values. **`rule_id` IS a permitted closed-enum property value** for `rule_*` events **and the `scan_report_finding_expanded` event** (the enum is the active rubric — a bounded set), per the scan-engine event allowlist below.
- `kind` ∈ {`skill`, `mcp_server`, `hook`, `plugin`, `rules`} (+ `all` on the filter event) is a permitted closed-enum value for the `scan_report_capability_filtered` / `scan_report_capability_expanded` / `scan_report_file_selected` events (the repo scan report's per-capability surface + the multi-file upload report's file-tab strip). `scan_report_file_selected` carries **only** `{kind}` — never the filename, slug, content hash, or token.
- `artifact_source` ∈ {`github`, `upload`} and `visibility` ∈ {`public`, `unlisted`} are permitted closed-enum values for the `homepage_scan_submitted` / `homepage_scan_panel_started` dual-mode scan events. **Never** the URL, filename, file bytes, or the unlisted `share_token` — the FE event is an intent signal; the backend `scan_submitted` (scan-engine allowlist below) is authoritative.

## Event allowlist — scan engine

The scan engine emits a closed enum of 16 events. The list is exhaustive — adding a new event is a `.claude/rules/telemetry.md` PR + an `app/observability/events.py` typed-helper PR. The helpers under `services/api/app/observability/events.py` are the only sanctioned emission path; raw `posthog.capture()` calls outside that module are a regression.

| # | Event | Properties (all bucketed / closed-enum) |
|---|---|---|
| 1 | `scan_submitted` | `source` ∈ {`submission`, `ingestion`, `rescan_drift`, `rescan_appeal`} (the trigger enum — **distinct from** `artifact_source`); `idempotency_cache_hit` (bool); `artifact_source` ∈ {`github`, `upload`}; `visibility` ∈ {`public`, `unlisted`}; `upload_size_bucket` ∈ {`<100KB`, `100KB-1MB`, `1-5MB`, `5-10MB`} (uploads only) |
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
| 15 | `promote_to_public` | `catalog_item_id_bucket` (hash%16) |
| 16 | `upload_rejected` | `reason` ∈ {`too_big`,`bad_type`,`binary`,`archive_rejected`,`rate_limited`}; optional `archive_sub` (the zip-safety / multi-file-batch sub-reason — `archive_rejected` now also covers multi-file batches: `nesting`/`dup_path`/`zip_slip`/`bad_path`) |

No raw IPs, no emails, no URLs, no `matched_content` strings — and **never the capability `share_token` or any path/filename content** (uploads). Bucketing helpers (`hash_to_bucket`, `latency_bucket`, `count_bucket`) live alongside the emit-helpers in `services/api/app/observability/events.py`.

## Ingestion events

5 backend + 1 frontend events. All bucketed/closed-enum, no PII.

| # | Event | Properties |
|---|---|---|
| 17 | `ingestion_cycle_started` | `source` (closed enum — the YAML-derived `SOURCE_NAMES` set, generated from `config/sources/*.yaml`); `cadence` (cron string) |
| 18 | `ingestion_cycle_completed` | `source`; `items_added_bucket` ∈ {`0`,`1-10`,`11-100`,`101-1k`,`1k+`}; `items_updated_bucket` (same); `duration_ms_bucket`; `http_304_ratio_bucket` ∈ {`0-25`,`25-50`,`50-75`,`75-100`} |
| 19 | `ingestion_cycle_failed` | `source`; `reason_enum` ∈ {`rate_limit`,`cf_challenge`,`http_5xx`,`timeout`,`permanent`,`other`} (`permanent` = a deterministic shape-drift / programming error — dead-lettered immediately, never retried; classified by `app/ingestion/framework/failure.py::classify_failure`, the shared ingestion+scan taxonomy) |
| 20 | `catalog_item_archived` | `source`; `reason_enum` ∈ {`404_timeline`,`maintainer_archived`,`yanked`} |
| 21 | `popularity_recompute_completed` | `top500_changed_count_bucket` ∈ {`0`,`1-10`,`11-100`,`101-1k`,`1k+`} |
| 22 | `sources_page_viewed` | (frontend, no properties) |

Backend emit helpers live in `app/observability/events.py` (`emit_ingestion_cycle_started`, `emit_ingestion_cycle_completed`, `emit_ingestion_cycle_failed`, `emit_ingestion_cycle_archived` → `catalog_item_archived`, `emit_popularity_recompute_completed`). Every helper logs via structlog **and** mirrors to PostHog through the shared `_emit` dispatch (no-op when `POSTHOG_PROJECT_KEY` is unset). The frontend `sources_page_viewed` event uses the existing `webapp/src/lib/analytics.ts` pattern.

## Install-telemetry event

1 backend event. Closed-enum, no PII.

| # | Event | Properties |
|---|---|---|
| 23 | `install_reported` | `agent` (the 8-agent closed enum — `claude-code`…`openclaw`); `kind` ∈ {`skill`,`mcp_server`,`hook`,`plugin`,`rules`} |

Fired by `app/observability/events.py::emit_install_reported` when the install CLI reports an **opt-in** install to `POST /api/v1/installs`. Never carries the slug, IP, or `cli_version` (those land only in the redacted `install_events` row). The CLI's own opt-out PostHog leg stays the single `command_invoked` event (`cli/src/core/telemetry.rs`) — `install_reported` is the **server-side** event.

## Agent-scan event

1 backend event, live at grading. Closed-enum + bucketed, no PII.

| # | Event | Properties |
|---|---|---|
| 24 | `agent_scan_completed` | `tier` ∈ {`green`,`yellow`,`orange`,`red`,`unscoped`} (the band); `findings_count_bucket` ∈ {`0`,`1`,`2-5`,`6-20`,`21+`}; `runtime` ∈ the 8 agent ids + `other` |

Fired by `app/observability/events.py::emit_agent_scan_completed` from the
`POST /agent-scans/{run_id}/submit` path after grading completes — best-effort
(wrapped in try/except so it never fails the scan). **No raw IP / slug / token /
agent output / transcript**, tagged `product: "saferskills"`; an unrecognized
`runtime` falls back to `other` (keeps the enum closed). The company-level
ASN/fingerprint signal is the separate write-only `agent_scan_telemetry` store
(`privacy.md` § agent_scan_telemetry), NOT this PostHog event.

> **Agent ids are single-sourced.** Both `install_reported.agent` and
> `agent_scan_completed.runtime` derive their closed agent-id set from
> `app/services/agent_compat.py` (`AgentName` / `ALL_AGENTS`) — `events.py` MUST
> NOT re-declare the list (`naming-conventions.md` § Agent identifiers).

## Error tracking

PostHog reports unexpected browser/SSR/API errors, failed background jobs and CLI crashes. Capture helpers must preserve application behavior when telemetry is disabled or unavailable.

- Preserve anonymous, memory-only browser analytics, no person profiles and disabled session replay. Do not copy authenticated-product identity or session behavior.
- Recursively sanitize error events before transport. Never send scanned content, submitted URLs, capability tokens, credentials, request bodies, frame locals or source context from user artifacts. Prefer exception classes, application stack frames and bounded operational metadata. Drop events when sanitation fails.
- Capture caught HTTP/job failures explicitly; unhandled exception hooks alone miss them. Deduplicate explicit capture and any logging bridge. Keep exporter failures out of that bridge.
- Attribute errors to their environment, service and release; preserve SDK chunk/binary identifiers needed for symbol resolution.
- Web deployment builds generate hidden maps, inject metadata before runtime image copying, upload to project 272364, then remove all `.map` files. `SOURCEMAP_UPLOAD=1` requires a private BuildKit upload secret and fails on upload errors; local/PR builds remain credential-free.
- CLI crash reporting retains its independent crash opt-outs and universal telemetry opt-outs. Upload native symbols for supported release targets; document unsupported symbolication rather than promising parity.
- Test missing configuration, offline behavior, bounded shutdown, duplicate suppression and adversarial redaction. Verify actual exception arrival and symbolication in the dedicated project after deployment.

## Outbound proxies — no PII

The `/api/v1/stats` `github_stars` proxy (`app/services/github_stars.py`) makes one cached hourly `api.github.com` call and stores **only the integer star count** — never request metadata, IPs, or user input. It is not a PostHog event and adds nothing to any analytics leg. (GitHub rate-limit *incidents* during scans are covered by the closed-enum `github_rate_limit_hit` / `github_rate_limit_recovered` events above.)

## OpenTelemetry

`OTEL_EXPORTER_OTLP_ENDPOINT` (optional; cf. `environment-config.md`). Server-side (backend) only.

- **Traces are exported now.** When the endpoint is set, `app/core/observability.py::_init_otel` wires a `TracerProvider` (`ParentBased(ALWAYS_ON)` sampler) + `BatchSpanProcessor(OTLPSpanExporter("{endpoint}/v1/traces"))` (HTTP/protobuf), and `app/main.py` auto-instruments FastAPI routes (`excluded_urls="health,ready,metrics"`), SQLAlchemy queries, and outbound HTTPX. The Resource carries `service.name=saferskills-api`, `service.version`, `deployment.environment`, and `service.instance.id` (the Fly Machine id). Export targets the **shared Grafana Vector** over Fly 6PN (`http://openlatch-observability[-staging].internal:4318`) — same org, so it ingests with no Vector edit.
- **Logs ↔ traces correlation**: `app/core/logging.py::inject_trace_context` stamps `trace_id` / `span_id` on every JSON log line, so Grafana cross-navigates Loki ↔ Tempo. Logs reach Loki via the Fly NATS drain (no app config).
- **Metrics are deferred.** The DB-pool observable gauges (`ingestion.db_pool.in_use` / `.available`) stay registered (harmless), but no metric reader/exporter is wired yet — a `/metrics` endpoint + a Vector `prometheus_scrape` block land in a separate openlatch-platform PR.
- **Never log raw scanned-artifact bytes** in span attributes. Hashes + sizes + counts only.

## Feature flags

Server-side flags are a thin wrapper over the PostHog client (`app/core/feature_flags.py`): `is_enabled(flag, distinct_id, default=False)` / `get_payload(...)`. Local evaluation when `POSTHOG_SERVER_KEY` (a `phx_…` personal API key) is set; else remote `/decide` via the project key; else the supplied default. The webapp mirror is `webapp/src/lib/feature-flags.ts` (`isFeatureEnabled`). Flag names are a **closed, reviewed set** — at launch exactly one example flag (`saferskills-example-flag`) exists and nothing real is gated by it. Every lookup degrades to its default (never breaks a request) when PostHog is unconfigured.

## Hard rules

1. **No PII anywhere.** PostHog analytics/errors and OTel span attributes — both destinations treat user input as untrusted and scrub it.
2. **Closed-enum event names + property values.** Adding an event = a `webapp/src/lib/analytics.ts` entry change reviewed in the PR.
3. **Bucketed numerics, never raw counts** in PostHog property values.
4. **Dedicated PostHog project 272364.** All environments use this project, separated by environment/service properties. Existing OTel/Grafana routing remains unchanged.
5. **Brand-independence**: when documentation or dashboards reference "the SaferSkills team", they reference SaferSkills maintainers only — never label cross-product dashboards.

## When to update this rule

| Change | Updates here |
|---|---|
| New install-telemetry property | "Install-telemetry event" table + `app/observability/events.py::emit_install_reported` |
| Agent-scan event property/runtime-enum change | "Agent-scan event" table + `app/observability/events.py::emit_agent_scan_completed` (`_RUNTIME_VALUES`) |
| New event prefix added | "Closed-enum event names" table + `webapp/src/lib/analytics.ts` |
| New scan-engine event | "Event allowlist — scan engine" table (bump the event count) + `services/api/app/observability/events.py` typed helper |
| New PostHog property value allowed | "Property allowlist" — re-verify the bucketed-numeric / closed-enum invariant |
| PostHog project / `product` discriminator change | "Purpose" + Hard rules #4 + the common metadata contract + `cli/src/core/telemetry.rs` |
| Error capture scope or privacy change | "Error tracking" + regression tests |
| New error-reporting surface or credential | "Error tracking" + `environment-config.md` + `ci-cd.md` |
| New OTel exporter / endpoint / instrumentor | "OpenTelemetry" + `app/core/observability.py` + `environment-config.md` |
| Metrics export wired (separate openlatch-platform PR) | "OpenTelemetry" — replace "Metrics are deferred" with the exporter + the Vector scrape block |
| New / changed feature flag | "Feature flags" (closed flag set) + `app/core/feature_flags.py` + `webapp/src/lib/feature-flags.ts` |
| New vendor (e.g. a separate logs sink) | New section here + `environment-config.md` |
