//! Typed endpoint wrappers + client-side name resolution (D-05-12, D-05-33).
//!
//! There is **no** server-side name resolver — resolution is client-side over
//! `GET /items?q=<name>` (FTS + trigram), with a `strsim` jaro_winkler
//! did-you-mean fallback when nothing matches exactly.

pub mod dto;

use dto::{
    CatalogItemSummary, CatalogListEnvelope, ChallengeResponse, HealthResponse, ItemDetailResponse,
    ScanRunReportDetail, ScanSubmitResponse, ScanUploadResponse,
};
use serde::Serialize;

use crate::cli::output::OutputConfig;
use crate::core::error::{SsError, ERR_ITEM_NOT_FOUND, ERR_SCAN_TIMEOUT};
use crate::core::http::ApiClient;

/// The custom header carrying a solved Proof-of-Work for CLI scan-submit.
const POW_HEADER: &str = "X-SaferSkills-CLI-PoW";

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

/// jaro_winkler floor for a did-you-mean suggestion (D-05-12).
const SUGGEST_THRESHOLD: f64 = 0.7;
/// Max did-you-mean suggestions to show.
const MAX_SUGGESTIONS: usize = 3;

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
    pub async fn submit_scan_url(
        &self,
        github_url: &str,
        visibility: &str,
        pow: &str,
    ) -> Result<ScanSubmitResponse, SsError> {
        self.client
            .post_json_for(
                "/api/v1/scans",
                &ScanSubmitBody {
                    github_url,
                    visibility,
                },
                &[(POW_HEADER, pow)],
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
        self.client
            .post_multipart("/api/v1/scans/upload", form, &[(POW_HEADER, pow)])
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
        let result = loop {
            match self.get_run(run_id).await {
                Ok(run) if is_terminal(&run) => break Ok(run),
                // Still running, OR not-yet-persisted (404 → ERR_ITEM_NOT_FOUND).
                Ok(_) => {}
                Err(e) if e.code == ERR_ITEM_NOT_FOUND => {}
                Err(e) => break Err(e),
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
    /// 1. `search_items(name)` → `data[]`.
    /// 2. Exact (case-insensitive) match on `display_name`, `slug`, or the
    ///    `<name>` portion of the slug's trailing `<kind>-<name>` segment.
    /// 3. Else the top-`N` jaro_winkler matches (≥ threshold) become a
    ///    did-you-mean `SS-E-1200`, with the `scan` fallback line.
    pub async fn resolve(&self, name: &str) -> Result<CatalogItemSummary, SsError> {
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

/// Build the not-found error, appending did-you-mean lines + the `scan`
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
    hint.push_str("Or submit a new scan: saferskills scan <github-url>");

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
        assert!(s.contains("saferskills scan <github-url>"));
    }

    #[test]
    fn not_found_error_without_suggestions_still_has_fallback() {
        let err = not_found_error("zzz", &[]);
        let s = err.suggestion.unwrap();
        assert!(!s.contains("Did you mean:"));
        assert!(s.contains("saferskills scan <github-url>"));
    }
}
