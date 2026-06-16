//! Typed endpoint wrappers + client-side name resolution (D-05-12, D-05-33).
//!
//! There is **no** server-side name resolver — resolution is client-side over
//! `GET /items?q=<name>` (FTS + trigram), with a `strsim` jaro_winkler
//! did-you-mean fallback when nothing matches exactly.

pub mod dto;

use std::collections::BTreeMap;

use dto::{
    AgentScanReport, AgentStatusResponse, BootstrapResponse, CatalogItemSummary,
    CatalogListEnvelope, ChallengeResponse, HealthResponse, ItemDetailResponse,
    ScanRunReportDetail, ScanSubmitResponse, ScanUploadResponse,
};
use serde::Serialize;

use crate::cli::output::OutputConfig;
use crate::core::error::{SsError, ERR_ITEM_NOT_FOUND, ERR_SCAN_TIMEOUT};
use crate::core::http::ApiClient;

/// The custom header carrying a solved Proof-of-Work for CLI scan-submit.
const POW_HEADER: &str = "X-SaferSkills-CLI-PoW";
/// The one-time run/submit token header (agent scan): gates pack-fetch + submit.
const RUN_TOKEN_HEADER: &str = "X-Agent-Run-Token";
/// Opt this submission out of company-level telemetry (the server records a minimal
/// `metadata-opted-out` row instead of the ASN/fingerprint signal).
const NO_TELEMETRY_HEADER: &str = "X-SaferSkills-No-Telemetry";

/// Build the PoW header list — an empty `pow` sends none (the server's
/// `_gate_submission` treats a *present* header as a PoW attempt, so an empty
/// value must be omitted, not sent blank).
fn pow_headers(pow: &str) -> Vec<(&str, &str)> {
    if pow.is_empty() {
        Vec::new()
    } else {
        vec![(POW_HEADER, pow)]
    }
}

/// Request body for `POST /api/v1/scans` (a GitHub-URL submit).
#[derive(Debug, Serialize)]
struct ScanSubmitBody<'a> {
    github_url: &'a str,
    visibility: &'a str,
}

/// The anonymous install-report body (`POST /api/v1/installs`, D-05-31).
#[derive(Debug, Serialize)]
pub struct InstallReport<'a> {
    pub slug: &'a str,
    pub agent: &'a str,
    pub kind: &'a str,
    pub cli_version: &'a str,
}

/// Body for `POST /api/v1/agent-scans/bootstrap` (mint a run + render the prompt).
/// `component_scan_run_id` + `kind_tally` are the best-effort local-capability
/// capture (omitted entirely when absent — the server treats a *missing* field as
/// "no components", same as a web mint).
#[derive(Debug, Serialize)]
struct BootstrapBody<'a> {
    platform: &'a str,
    agent_name: &'a str,
    runtime: &'a str,
    visibility: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    component_scan_run_id: Option<&'a str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    kind_tally: Option<&'a BTreeMap<String, u32>>,
}

/// The faceted query for [`Api::list_items`] — the `search` command's filter
/// state lowered to API query params. Every field maps 1:1 to an existing
/// `GET /api/v1/items` query parameter; building this is a pure transform
/// (`to_params`), unit-tested independently of any network call.
#[derive(Debug, Clone, Default)]
pub struct CatalogQuery {
    /// Free-text search (FTS + pg_trgm fuzzy). `None`/empty → trending list.
    pub q: Option<String>,
    /// Repeatable `kind` filter (`skill` | `mcp_server` | `hook` | …).
    pub kinds: Vec<String>,
    /// Repeatable `agent` compatibility filter (canonical kebab ids).
    pub agents: Vec<String>,
    /// Repeatable `scan_tier` filter (`green` | `yellow` | `orange` | `red`).
    pub scan_tiers: Vec<String>,
    /// Minimum aggregate score (0–100). `0`/`None` omits the param.
    pub score_min: Option<u8>,
    /// Server sort key (e.g. `most_installed`). `None` → server default.
    pub sort: Option<String>,
    /// Page size (`limit`, 1–100).
    pub limit: u32,
    /// Include low/empty quality_tier items (`showLowQuality`).
    pub show_low_quality: bool,
}

impl CatalogQuery {
    /// Lower the faceted query to repeatable `(key, value)` API params. Keys are
    /// `'static`; values are owned (the caller borrows them into the request).
    /// An empty `q`, a zero `score_min`, and `show_low_quality=false` are omitted
    /// (they are the server defaults).
    pub fn to_params(&self) -> Vec<(&'static str, String)> {
        let mut params: Vec<(&'static str, String)> = Vec::new();
        if let Some(q) = self.q.as_deref().map(str::trim).filter(|s| !s.is_empty()) {
            params.push(("q", q.to_string()));
        }
        for k in &self.kinds {
            params.push(("kind", k.clone()));
        }
        for a in &self.agents {
            params.push(("agent", a.clone()));
        }
        for t in &self.scan_tiers {
            params.push(("scan_tier", t.clone()));
        }
        if let Some(s) = self.score_min.filter(|s| *s > 0) {
            params.push(("score_min", s.to_string()));
        }
        if let Some(sort) = self.sort.as_deref().filter(|s| !s.is_empty()) {
            params.push(("sort", sort.to_string()));
        }
        params.push(("limit", self.limit.to_string()));
        if self.show_low_quality {
            params.push(("showLowQuality", "true".to_string()));
        }
        params
    }
}

/// jaro_winkler floor for a did-you-mean suggestion (D-05-12).
const SUGGEST_THRESHOLD: f64 = 0.7;
/// Max did-you-mean suggestions to show.
const MAX_SUGGESTIONS: usize = 3;
/// How long a status poll tolerates *continuous* request failures before giving up.
/// A single slow/failed poll must not abort a run that is fine server-side (the
/// agent wait is minutes long; the local API can blip under load), but a genuinely
/// unreachable API should still fail in bounded time rather than spin to the
/// full client deadline. Reset on any successful (or "pending") poll.
const POLL_FAILURE_GRACE: std::time::Duration = std::time::Duration::from_secs(60);

/// Typed API surface the CLI consumes.
#[derive(Debug, Clone)]
pub struct Api {
    client: ApiClient,
}

impl Api {
    /// Build against an already-resolved API base origin.
    pub fn new(base: String) -> Result<Self, SsError> {
        Ok(Self {
            client: ApiClient::new(base)?,
        })
    }

    /// The resolved API base origin (for building report URLs).
    pub fn base(&self) -> &str {
        self.client.base()
    }

    /// `GET /api/v1/items?q=<q>[&kind=<kind>]`.
    pub async fn search_items(
        &self,
        q: &str,
        kind: Option<&str>,
    ) -> Result<CatalogListEnvelope, SsError> {
        let mut query: Vec<(&str, &str)> = vec![("q", q)];
        if let Some(k) = kind {
            query.push(("kind", k));
        }
        self.client.get("/api/v1/items", &query).await
    }

    /// `GET /api/v1/items` with the full faceted-query parameter set — the
    /// backing fetch for the interactive `search` TUI + its headless `--json`
    /// path. Repeatable `kind`/`agent`/`scan_tier` are emitted once per value;
    /// every facet maps to an existing server query param (no backend change).
    pub async fn list_items(&self, query: &CatalogQuery) -> Result<CatalogListEnvelope, SsError> {
        // Own the value strings first, then borrow into the `&[(&str, &str)]`
        // shape `ApiClient::get` expects (keys are 'static; values are owned).
        let owned = query.to_params();
        let borrowed: Vec<(&str, &str)> = owned.iter().map(|(k, v)| (*k, v.as_str())).collect();
        self.client.get("/api/v1/items", &borrowed).await
    }

    /// `GET /api/v1/items/{slug}`.
    pub async fn get_item(&self, slug: &str) -> Result<ItemDetailResponse, SsError> {
        self.client.get(&format!("/api/v1/items/{slug}"), &[]).await
    }

    /// `GET /api/v1/scans/runs/{run_id}` (the repo report / roll-up).
    pub async fn get_run(&self, run_id: &str) -> Result<ScanRunReportDetail, SsError> {
        self.client
            .get(&format!("/api/v1/scans/runs/{run_id}"), &[])
            .await
    }

    /// `GET /api/v1/health`.
    pub async fn health(&self) -> Result<HealthResponse, SsError> {
        self.client.get("/api/v1/health", &[]).await
    }

    /// `GET /api/v1/scans/cli-challenge` — a stateless Proof-of-Work challenge
    /// for the CLI scan-submit gate (D-05-30). 503 when the server has no PoW
    /// secret (dev/test) — the caller surfaces it.
    pub async fn get_cli_challenge(&self) -> Result<ChallengeResponse, SsError> {
        self.client.get("/api/v1/scans/cli-challenge", &[]).await
    }

    /// `POST /api/v1/scans` — submit a GitHub URL, carrying the solved PoW header.
    /// An empty `pow` sends **no** PoW header (loopback callers are gate-exempt
    /// server-side, so a local dev API needs none — see `scan::obtain_pow_if_needed`).
    pub async fn submit_scan_url(
        &self,
        github_url: &str,
        visibility: &str,
        pow: &str,
    ) -> Result<ScanSubmitResponse, SsError> {
        let headers = pow_headers(pow);
        self.client
            .post_json_for(
                "/api/v1/scans",
                &ScanSubmitBody {
                    github_url,
                    visibility,
                },
                &headers,
            )
            .await
    }

    /// `POST /api/v1/scans/upload` — submit local content as a `.zip`, carrying
    /// the solved PoW header. The multipart `file` part + `visibility`/`kind`
    /// text fields match the backend `fields.get(...)` names exactly.
    pub async fn submit_scan_upload(
        &self,
        zip_bytes: Vec<u8>,
        filename: &str,
        visibility: &str,
        kind: Option<&str>,
        pow: &str,
    ) -> Result<ScanUploadResponse, SsError> {
        let part = reqwest::multipart::Part::bytes(zip_bytes)
            .file_name(filename.to_string())
            .mime_str("application/zip")
            .map_err(|e| {
                SsError::new(
                    ERR_SCAN_TIMEOUT,
                    format!("Failed to build upload part: {e}"),
                )
            })?;
        let mut form = reqwest::multipart::Form::new()
            .part("file", part)
            .text("visibility", visibility.to_string());
        if let Some(k) = kind {
            form = form.text("kind", k.to_string());
        }
        let headers = pow_headers(pow);
        self.client
            .post_multipart("/api/v1/scans/upload", form, &headers)
            .await
    }

    /// Poll `GET /api/v1/scans/runs/{run_id}` until the run reaches a terminal
    /// status or `timeout` elapses. A 404 is treated as "still pending" (the run
    /// row is visible only once persisted). `ERR_SCAN_TIMEOUT` on timeout.
    pub async fn wait_for_run(
        &self,
        run_id: &str,
        output: &OutputConfig,
        timeout: std::time::Duration,
    ) -> Result<ScanRunReportDetail, SsError> {
        let spinner = output.create_spinner("Scanning…");
        let deadline = std::time::Instant::now() + timeout;
        // Resilient poll (see `wait_for_agent_run`): a not-yet-persisted 404 is
        // "pending" (resets the failure window), other transient errors are
        // tolerated, and only `POLL_FAILURE_GRACE` of continuous failure (or the
        // deadline) aborts.
        let mut failing_since: Option<std::time::Instant> = None;
        let result = loop {
            match self.get_run(run_id).await {
                Ok(run) if is_terminal(&run) => break Ok(run),
                // Still running, OR not-yet-persisted (404 → ERR_ITEM_NOT_FOUND).
                Ok(_) => failing_since = None,
                Err(e) if e.code == ERR_ITEM_NOT_FOUND => failing_since = None,
                Err(e) => {
                    let since = failing_since.get_or_insert_with(std::time::Instant::now);
                    if since.elapsed() >= POLL_FAILURE_GRACE {
                        break Err(e);
                    }
                }
            }
            if std::time::Instant::now() >= deadline {
                break Err(SsError::new(
                    ERR_SCAN_TIMEOUT,
                    "The scan did not finish before the client timeout.",
                )
                .with_suggestion(
                    "Re-run, or open the report URL in a browser to watch progress.",
                ));
            }
            tokio::time::sleep(std::time::Duration::from_millis(1500)).await;
        };
        if let Some(pb) = spinner {
            pb.finish_and_clear();
        }
        result
    }

    // ─── Agent Scan (I-5.5 Phase 3) ──────────────────────────────────────────

    /// `POST /api/v1/agent-scans/bootstrap` — mint a run + render the bootstrap
    /// prompt. Carries the solved PoW (empty `pow` ⇒ no header; loopback-exempt).
    /// `component_scan_run_id` + `kind_tally` are the best-effort component capture
    /// (both `None` on the manual `--print-skill` path).
    #[allow(clippy::too_many_arguments)] // a flat 1:1 HTTP-body wrapper, not a unit to refactor
    pub async fn bootstrap_agent_scan(
        &self,
        platform: &str,
        agent_name: &str,
        runtime: &str,
        visibility: &str,
        component_scan_run_id: Option<&str>,
        kind_tally: Option<&BTreeMap<String, u32>>,
        pow: &str,
    ) -> Result<BootstrapResponse, SsError> {
        let headers = pow_headers(pow);
        self.client
            .post_json_for(
                "/api/v1/agent-scans/bootstrap",
                &BootstrapBody {
                    platform,
                    agent_name,
                    runtime,
                    visibility,
                    component_scan_run_id,
                    kind_tally,
                },
                &headers,
            )
            .await
    }

    /// `GET /api/v1/agent-scans/{run_id}/pack` (token-gated) → `(body, key_id, sig)`.
    /// The signed-pack bytes + the `X-Pack-Key-Id` / `X-Pack-Signature` headers the
    /// CLI verifies with `verify_strict` before printing the prompt.
    pub async fn get_pack_bytes(
        &self,
        run_id: &str,
        token: &str,
    ) -> Result<(Vec<u8>, Option<String>, Option<String>), SsError> {
        let (body, picked) = self
            .client
            .get_bytes_with_headers(
                &format!("/api/v1/agent-scans/{run_id}/pack"),
                &[(RUN_TOKEN_HEADER, token)],
                &["x-pack-key-id", "x-pack-signature"],
            )
            .await?;
        let mut it = picked.into_iter();
        let key_id = it.next().flatten();
        let sig = it.next().flatten();
        Ok((body, key_id, sig))
    }

    /// `GET /api/v1/agent-scans/{run_id}/status` (token-authed) — the poll target.
    pub async fn get_agent_status(
        &self,
        run_id: &str,
        token: &str,
    ) -> Result<AgentStatusResponse, SsError> {
        self.client
            .get_with_headers(
                &format!("/api/v1/agent-scans/{run_id}/status"),
                &[],
                &[(RUN_TOKEN_HEADER, token)],
            )
            .await
    }

    /// `GET /api/v1/agent-scans/{run_id}` — the public graded report.
    pub async fn get_agent_run(&self, run_id: &str) -> Result<AgentScanReport, SsError> {
        self.client
            .get(&format!("/api/v1/agent-scans/{run_id}"), &[])
            .await
    }

    /// `GET /api/v1/agent-scans/r/{share_token}` — the unlisted (private) report.
    pub async fn get_agent_run_private(
        &self,
        share_token: &str,
    ) -> Result<AgentScanReport, SsError> {
        self.client
            .get(&format!("/api/v1/agent-scans/r/{share_token}"), &[])
            .await
    }

    /// `POST /api/v1/agent-scans/{run_id}/abort` (token-authed, 204) — discard a run
    /// (best-effort cancel, e.g. on a pack-signature mismatch).
    pub async fn abort_agent_run(&self, run_id: &str, token: &str) -> Result<(), SsError> {
        self.client
            .post_for_status(
                &format!("/api/v1/agent-scans/{run_id}/abort"),
                &[(RUN_TOKEN_HEADER, token)],
            )
            .await
    }

    /// `POST /api/v1/agent-scans/{run_id}/submit` with a `text/plain` paste-back
    /// body (the server decodes it). Carries the PoW + one-time run token, and the
    /// telemetry opt-out header when `no_telemetry` is set.
    pub async fn submit_agent_blob(
        &self,
        run_id: &str,
        token: &str,
        body: String,
        pow: &str,
        no_telemetry: bool,
    ) -> Result<AgentScanReport, SsError> {
        let mut headers = pow_headers(pow);
        headers.push((RUN_TOKEN_HEADER, token));
        if no_telemetry {
            headers.push((NO_TELEMETRY_HEADER, "1"));
        }
        self.client
            .post_text_for(
                &format!("/api/v1/agent-scans/{run_id}/submit"),
                body,
                "text/plain; charset=utf-8",
                &headers,
            )
            .await
    }

    /// Poll `GET /agent-scans/{run_id}/status` (token-authed) until the run reaches a
    /// terminal state (`graded` / `published` / `aborted`) or `timeout` elapses.
    /// Returns the terminal status; the caller then fetches the full report.
    pub async fn wait_for_agent_run(
        &self,
        run_id: &str,
        token: &str,
        output: &OutputConfig,
        timeout: std::time::Duration,
    ) -> Result<AgentStatusResponse, SsError> {
        let spinner = output.create_spinner("Waiting for the agent to submit results…");
        let deadline = std::time::Instant::now() + timeout;
        // Tolerate transient API hiccups during the long human-in-the-loop wait: a
        // slow or briefly-failing poll must not abort a run that is fine
        // server-side. Give up only when the API has been *continuously* failing
        // for `POLL_FAILURE_GRACE` (covers a dead API / a rejected token in bounded
        // time), the deadline passes, or the run reaches a terminal state.
        let mut failing_since: Option<std::time::Instant> = None;
        let result = loop {
            match self.get_agent_status(run_id, token).await {
                Ok(s) if is_agent_terminal(&s.status) => break Ok(s),
                Ok(_) => failing_since = None,
                Err(e) => {
                    let since = failing_since.get_or_insert_with(std::time::Instant::now);
                    if since.elapsed() >= POLL_FAILURE_GRACE {
                        break Err(e);
                    }
                }
            }
            if std::time::Instant::now() >= deadline {
                break Err(SsError::new(
                    ERR_SCAN_TIMEOUT,
                    "No results were submitted before the client timeout.",
                )
                .with_suggestion(
                    "If your agent printed a SAFERSKILLS-AGENTSCAN blob, submit it with \
                     `saferskills agent --submit-blob <file>`.",
                ));
            }
            tokio::time::sleep(std::time::Duration::from_millis(1500)).await;
        };
        if let Some(pb) = spinner {
            pb.finish_and_clear();
        }
        result
    }

    /// `GET /api/v1/items/{slug}/download` — the stored snapshot `.zip` bytes,
    /// the source for a skill folder copy (D-05-16).
    pub async fn download_item_zip(&self, slug: &str) -> Result<Vec<u8>, SsError> {
        self.client
            .get_bytes(&format!("/api/v1/items/{slug}/download"))
            .await
    }

    /// `POST /api/v1/installs` — report an anonymous install (D-05-31). Fail-open:
    /// the caller swallows the error so a failed report never fails the install.
    pub async fn report_install(
        &self,
        slug: &str,
        agent: &str,
        kind: &str,
        cli_version: &str,
    ) -> Result<(), SsError> {
        self.client
            .post_json(
                "/api/v1/installs",
                &InstallReport {
                    slug,
                    agent,
                    kind,
                    cli_version,
                },
            )
            .await
    }

    /// Resolve a typed name to a single catalog item.
    ///
    /// 0. **Slug fast-path.** The webapp Install card emits the full catalog
    ///    slug (`<org>--<repo>--<kind>-<name>`), which never surfaces via FTS
    ///    `q=` (the hyphenated slug tokenizes to nothing and the display name is
    ///    unrelated), so `install <slug>` would 404 despite the item existing.
    ///    Any value carrying the `--` slug separator is therefore resolved by a
    ///    direct `GET /items/{slug}` first; a 404 falls through to fuzzy search.
    /// 1. `search_items(name)` → `data[]`.
    /// 2. Exact (case-insensitive) match on `display_name`, `slug`, or the
    ///    `<name>` portion of the slug's trailing `<kind>-<name>` segment.
    /// 3. Else the top-`N` jaro_winkler matches (≥ threshold) become a
    ///    did-you-mean `SS-E-1200`, with the `capability` fallback line.
    pub async fn resolve(&self, name: &str) -> Result<CatalogItemSummary, SsError> {
        if name.contains("--") {
            match self.get_item(name).await {
                Ok(detail) => return Ok(detail.item),
                // Not a live slug — fall through to fuzzy did-you-mean search.
                Err(e) if e.code == ERR_ITEM_NOT_FOUND => {}
                Err(e) => return Err(e),
            }
        }

        let envelope = self.search_items(name, None).await?;
        let data = envelope.data;

        if let Some(exact) = data.iter().find(|i| is_exact_match(i, name)) {
            return Ok(exact.clone());
        }

        // Rank remaining candidates by the better of display-name / slug score.
        let mut ranked: Vec<(&CatalogItemSummary, f64)> = data
            .iter()
            .map(|i| (i, similarity(name, i)))
            .filter(|(_, s)| *s >= SUGGEST_THRESHOLD)
            .collect();
        ranked.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        let suggestions: Vec<&CatalogItemSummary> = ranked
            .into_iter()
            .take(MAX_SUGGESTIONS)
            .map(|(i, _)| i)
            .collect();

        Err(not_found_error(name, &suggestions))
    }
}

/// Whether an agent-scan run status is terminal (`graded`/`published` = done;
/// `aborted` = cancelled). `created`/`fetched`/`submitted` are still pending.
fn is_agent_terminal(status: &str) -> bool {
    matches!(status, "graded" | "published" | "aborted")
}

/// Whether a polled run has reached a terminal state. Prefers the explicit
/// `status` (`completed`/`failed`); falls back to "has capabilities" for an
/// older server that omits the field.
fn is_terminal(run: &ScanRunReportDetail) -> bool {
    match run.status.as_deref() {
        Some("completed") | Some("failed") => true,
        Some(_) => false,
        None => run.capability_count > 0 && !run.capabilities.is_empty(),
    }
}

/// The `<name>` portion of a slug's trailing `<kind>-<name>` segment, used for a
/// friendly exact match (`github-mcp` matches `acme--repo--mcp-server-github`? —
/// the trailing segment is `mcp-server-github`; we also match the whole segment).
fn slug_tail(slug: &str) -> &str {
    slug.rsplit("--").next().unwrap_or(slug)
}

fn is_exact_match(item: &CatalogItemSummary, name: &str) -> bool {
    item.display_name.eq_ignore_ascii_case(name)
        || item.slug.eq_ignore_ascii_case(name)
        || slug_tail(&item.slug).eq_ignore_ascii_case(name)
}

fn similarity(name: &str, item: &CatalogItemSummary) -> f64 {
    let lname = name.to_ascii_lowercase();
    let by_display = strsim::jaro_winkler(&lname, &item.display_name.to_ascii_lowercase());
    let by_tail = strsim::jaro_winkler(&lname, &slug_tail(&item.slug).to_ascii_lowercase());
    by_display.max(by_tail)
}

/// Build the not-found error, appending did-you-mean lines + the `capability`
/// fallback into the suggestion field (rendered by `print_error`).
fn not_found_error(name: &str, suggestions: &[&CatalogItemSummary]) -> SsError {
    let mut hint = String::new();
    if !suggestions.is_empty() {
        hint.push_str("Did you mean:\n");
        for s in suggestions {
            let score = s
                .latest_scan_score
                .map(|v| v.to_string())
                .unwrap_or_else(|| "—".to_string());
            let tier = s.latest_scan_tier.map(|t| t.label()).unwrap_or("Unscoped");
            hint.push_str(&format!(
                "    \u{2022} {}  ({score}/100, {tier})\n",
                suggestion_name(s)
            ));
        }
    }
    hint.push_str("Or submit a new scan: saferskills capability <github-url>");

    SsError::new(
        ERR_ITEM_NOT_FOUND,
        format!("Item not found in catalog: \"{name}\""),
    )
    .with_suggestion(hint)
}

/// The friendliest name to show in a suggestion: the slug tail (closest to what
/// a user types) falling back to the display name.
fn suggestion_name(item: &CatalogItemSummary) -> String {
    let tail = slug_tail(&item.slug);
    if tail.is_empty() {
        item.display_name.clone()
    } else {
        tail.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use dto::Tier;

    fn item(
        slug: &str,
        display: &str,
        score: Option<u8>,
        tier: Option<Tier>,
    ) -> CatalogItemSummary {
        CatalogItemSummary {
            id: "id".into(),
            slug: slug.into(),
            kind: "mcp_server".into(),
            display_name: display.into(),
            description: None,
            github_url: None,
            github_org: None,
            github_repo: None,
            source_kind: None,
            popularity_tier: "emerging".into(),
            popularity_score: 0,
            latest_scan_score: score,
            latest_scan_tier: tier,
            latest_scan_at: None,
            findings_count: 0,
            registries: vec![],
            agent_compatibility: vec![],
            updated_at: None,
        }
    }

    #[test]
    fn exact_match_on_slug_tail() {
        let it = item(
            "acme--repo--mcp-server-github",
            "GitHub MCP",
            Some(87),
            Some(Tier::Green),
        );
        assert!(is_exact_match(&it, "mcp-server-github"));
        assert!(is_exact_match(&it, "GitHub MCP"));
        assert!(!is_exact_match(&it, "totally-different"));
    }

    #[test]
    fn similarity_prefers_close_names() {
        let it = item("acme--repo--mcp-server-github", "GitHub MCP", None, None);
        assert!(similarity("github-mcp", &it) > 0.0);
        assert!(similarity("github mcp", &it) > similarity("zzzzzz", &it));
    }

    #[test]
    fn not_found_error_lists_suggestions_and_scan_fallback() {
        let it = item(
            "a--b--mcp-server-github",
            "GitHub MCP",
            Some(87),
            Some(Tier::Green),
        );
        let err = not_found_error("ghub-mcp", &[&it]);
        assert_eq!(err.exit_code(), 3);
        let s = err.suggestion.unwrap();
        assert!(s.contains("Did you mean:"));
        assert!(s.contains("(87/100, Green)"));
        assert!(s.contains("saferskills capability <github-url>"));
    }

    #[test]
    fn not_found_error_without_suggestions_still_has_fallback() {
        let err = not_found_error("zzz", &[]);
        let s = err.suggestion.unwrap();
        assert!(!s.contains("Did you mean:"));
        assert!(s.contains("saferskills capability <github-url>"));
    }

    #[test]
    fn catalog_query_default_emits_only_limit() {
        // An all-default trending query: no q, no facets → just `limit`.
        let q = CatalogQuery {
            limit: 50,
            ..CatalogQuery::default()
        };
        let p = q.to_params();
        assert_eq!(p, vec![("limit", "50".to_string())]);
    }

    #[test]
    fn catalog_query_repeats_facets_and_omits_defaults() {
        let q = CatalogQuery {
            q: Some("  redis  ".into()),
            kinds: vec!["skill".into(), "mcp_server".into()],
            agents: vec!["claude-code".into()],
            scan_tiers: vec!["green".into(), "yellow".into()],
            score_min: Some(70),
            sort: Some("most_installed".into()),
            limit: 25,
            show_low_quality: true,
        };
        let p = q.to_params();
        // q is trimmed; each repeatable facet appears once per value.
        assert!(p.contains(&("q", "redis".to_string())));
        assert_eq!(p.iter().filter(|(k, _)| *k == "kind").count(), 2);
        assert_eq!(p.iter().filter(|(k, _)| *k == "agent").count(), 1);
        assert_eq!(p.iter().filter(|(k, _)| *k == "scan_tier").count(), 2);
        assert!(p.contains(&("score_min", "70".to_string())));
        assert!(p.contains(&("sort", "most_installed".to_string())));
        assert!(p.contains(&("limit", "25".to_string())));
        assert!(p.contains(&("showLowQuality", "true".to_string())));
    }

    #[test]
    fn bootstrap_body_omits_component_fields_when_none() {
        // A web/manual mint (no local capture) must omit both fields entirely, so
        // the server treats them as absent (== no components), not null.
        let body = BootstrapBody {
            platform: "claude-code",
            agent_name: "swift-otter",
            runtime: "claude-code",
            visibility: "public",
            component_scan_run_id: None,
            kind_tally: None,
        };
        let v = serde_json::to_value(&body).unwrap();
        assert!(v.get("component_scan_run_id").is_none());
        assert!(v.get("kind_tally").is_none());
        assert_eq!(v["platform"], "claude-code");
    }

    #[test]
    fn bootstrap_body_includes_component_fields_when_present() {
        let mut tally = BTreeMap::new();
        tally.insert("skill".to_string(), 3u32);
        tally.insert("mcp_server".to_string(), 1u32);
        let body = BootstrapBody {
            platform: "universal",
            agent_name: "swift-otter",
            runtime: "other",
            visibility: "unlisted",
            component_scan_run_id: Some("run-123"),
            kind_tally: Some(&tally),
        };
        let v = serde_json::to_value(&body).unwrap();
        assert_eq!(v["component_scan_run_id"], "run-123");
        assert_eq!(v["kind_tally"]["skill"], 3);
        assert_eq!(v["kind_tally"]["mcp_server"], 1);
    }

    #[test]
    fn catalog_query_omits_empty_q_and_zero_score_min() {
        let q = CatalogQuery {
            q: Some("   ".into()),
            score_min: Some(0),
            limit: 50,
            ..CatalogQuery::default()
        };
        let p = q.to_params();
        assert!(!p.iter().any(|(k, _)| *k == "q"));
        assert!(!p.iter().any(|(k, _)| *k == "score_min"));
        assert!(!p.iter().any(|(k, _)| *k == "showLowQuality"));
    }
}
