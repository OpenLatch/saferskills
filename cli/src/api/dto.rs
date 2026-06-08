//! Hand-written wire DTOs for the SaferSkills public API (D-05-08).
//!
//! These mirror the snake_case JSON the API emits (`OrmBaseModel.model_dump
//! (by_alias=false)`); paginated lists deserialize the `data` envelope key (NOT
//! `items`, per `naming-conventions.md`). There is **no** typify/codegen here —
//! the CLI is an API consumer, not part of the repo's 8-generator pipeline. A
//! contract test (`tests/contract.rs`) deserializes `services/api/openapi.json`
//! component examples into these structs and fails on drift, which is the
//! honest schema-fidelity gate.
//!
//! Resilience (prime invariant: never panic on malformed input): unknown enum
//! values fall through to an `Unknown` variant, optional/extra fields default,
//! and unknown object keys are ignored (no `deny_unknown_fields`).

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

/// Finding-severity ladder (D-02). `info` carries weight 0.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Severity {
    Info,
    Low,
    Medium,
    High,
    Critical,
    /// Forward-compat catch-all for a severity this CLI build doesn't know.
    #[serde(other)]
    Unknown,
}

impl Severity {
    /// Ordering rank for "highest severity wins" gating (D-05-19). `Unknown`
    /// sorts at the bottom so it never silently escalates a gate.
    pub fn rank(self) -> u8 {
        match self {
            Severity::Critical => 4,
            Severity::High => 3,
            Severity::Medium => 2,
            Severity::Low => 1,
            Severity::Info | Severity::Unknown => 0,
        }
    }
}

/// Score-tier band (PRD §5.1). `unscoped` = never scanned.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Tier {
    Green,
    Yellow,
    Orange,
    Red,
    Unscoped,
    /// Forward-compat catch-all for a tier this CLI build doesn't know.
    #[serde(other)]
    Unknown,
}

impl Tier {
    /// Human label for a tier (e.g. `"Green"`), for plain-text contexts like
    /// did-you-mean suggestions that render without ANSI color.
    pub fn label(self) -> &'static str {
        match self {
            Tier::Green => "Green",
            Tier::Yellow => "Yellow",
            Tier::Orange => "Orange",
            Tier::Red => "Red",
            Tier::Unscoped => "Unscoped",
            Tier::Unknown => "Unknown",
        }
    }
}

/// One line of a finding's matched-content evidence window (report-DTO only,
/// snapshot-sourced — never a trace field).
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct EvidenceLine {
    pub line_no: u32,
    pub text: String,
    pub hit: bool,
}

/// The matched-line window shown verbatim on a finding card.
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct EvidenceExcerpt {
    pub file: String,
    #[serde(default)]
    pub lang: Option<String>,
    #[serde(default)]
    pub lines: Vec<EvidenceLine>,
    #[serde(default)]
    pub truncated: bool,
}

impl EvidenceExcerpt {
    /// The first matched (`hit`) line, for a single-line evidence summary.
    pub fn hit_line(&self) -> Option<&EvidenceLine> {
        self.lines
            .iter()
            .find(|l| l.hit)
            .or_else(|| self.lines.first())
    }
}

/// A single rule fire on a scanned artifact (report DTO, snake_case).
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct FindingResponse {
    pub id: String,
    pub rule_id: String,
    pub severity: Severity,
    pub sub_score: String,
    pub penalty: i32,
    pub status_at_scan: String,
    pub file_path: String,
    pub line_start: u32,
    #[serde(default)]
    pub line_end: Option<u32>,
    pub matched_content_sha256: String,
    pub remediation_link: String,
    pub rubric_version: String,
    #[serde(default)]
    pub evidence_excerpt: Option<EvidenceExcerpt>,
    // Explainable-finding prose, inlined server-side onto the report (D-05-32
    // reversed — the CLI renders straight from the finding, no rule corpus
    // fetch). All `#[serde(default)]` for forward-compat: a degraded finding (no
    // content entry) carries None and the CLI falls back to rule_id +
    // remediation_link.
    #[serde(default)]
    pub title: Option<String>,
    #[serde(default)]
    pub explanation: Option<String>,
    #[serde(default)]
    pub category_label: Option<String>,
    #[serde(default)]
    pub severity_rationale: Option<String>,
    #[serde(default)]
    pub remediation: Option<FindingRemediation>,
}

/// An Avoid → Safer before/after pair on an inlined finding remediation.
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct SaferPattern {
    pub before: String,
    pub after: String,
}

/// How to fix a finding — inlined onto the report finding (snake_case).
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct FindingRemediation {
    pub action: String,
    #[serde(default)]
    pub steps: Option<Vec<String>>,
    #[serde(default)]
    pub safer_pattern: Option<SaferPattern>,
}

/// A catalog item as it appears in list responses + `item` on the detail page.
/// (The API's `CatalogItemDetail` is a superset — its extra keys are ignored.)
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CatalogItemSummary {
    pub id: String,
    pub slug: String,
    pub kind: String,
    pub display_name: String,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub github_url: Option<String>,
    #[serde(default)]
    pub github_org: Option<String>,
    #[serde(default)]
    pub github_repo: Option<String>,
    #[serde(default)]
    pub source_kind: Option<String>,
    pub popularity_tier: String,
    #[serde(default)]
    pub popularity_score: i64,
    #[serde(default)]
    pub latest_scan_score: Option<u8>,
    #[serde(default)]
    pub latest_scan_tier: Option<Tier>,
    #[serde(default)]
    pub latest_scan_at: Option<String>,
    #[serde(default)]
    pub findings_count: i64,
    #[serde(default)]
    pub registries: Vec<String>,
    #[serde(default)]
    pub agent_compatibility: Vec<String>,
    #[serde(default)]
    pub updated_at: Option<String>,
}

/// Paginated catalog list envelope. The array key is `data` (NOT `items`).
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CatalogListEnvelope {
    #[serde(default)]
    pub data: Vec<CatalogItemSummary>,
    #[serde(default)]
    pub next_cursor: Option<String>,
    #[serde(default)]
    pub total_count: i64,
    #[serde(default)]
    pub page: i64,
    #[serde(default)]
    pub total_pages: i64,
    #[serde(default)]
    pub page_size: i64,
}

/// A per-capability scan report (`GET /scans/{scan_id}`, and `latest_scan` on
/// the item detail).
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ScanReportDetail {
    pub id: String,
    #[serde(default)]
    pub github_url: Option<String>,
    pub slug: String,
    pub display_name: String,
    pub aggregate_score: u8,
    pub tier: Tier,
    #[serde(default)]
    pub sub_scores: BTreeMap<String, i64>,
    #[serde(default)]
    pub findings: Vec<FindingResponse>,
    #[serde(default)]
    pub scanned_at: Option<String>,
    #[serde(default)]
    pub rubric_version: Option<String>,
    #[serde(default)]
    pub engine_version: Option<String>,
    #[serde(default)]
    pub component_path: Option<String>,
    #[serde(default)]
    pub scan_run_id: Option<String>,
}

/// The item-detail response (`GET /items/{slug}`). Only the fields the CLI
/// reads are modeled; the rest of the rich page payload is ignored.
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ItemDetailResponse {
    pub item: CatalogItemSummary,
    #[serde(default)]
    pub latest_scan: Option<ScanReportDetail>,
}

/// One capability within a repo scan run (`GET /scans/runs/{run_id}`).
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CapabilityRow {
    pub kind: String,
    pub name: String,
    #[serde(default)]
    pub component_path: Option<String>,
    pub aggregate_score: u8,
    pub tier: Tier,
    pub scan_id: String,
    pub catalog_slug: String,
    #[serde(default)]
    pub sub_scores: BTreeMap<String, i64>,
    #[serde(default)]
    pub findings: Vec<FindingResponse>,
}

/// A repo scan run — the roll-up the CLI's `scan` / `scan --local` report (the
/// run report IS the roll-up).
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ScanRunReportDetail {
    pub id: String,
    #[serde(default)]
    pub github_url: Option<String>,
    pub repo_aggregate_score: u8,
    pub repo_tier: Tier,
    #[serde(default)]
    pub kind_tally: BTreeMap<String, i64>,
    #[serde(default)]
    pub capability_count: i64,
    #[serde(default)]
    pub capabilities: Vec<CapabilityRow>,
    /// `pending` | `running` | `completed` | `failed`. Free-form so an unknown
    /// status never breaks polling; absent on older servers.
    #[serde(default)]
    pub status: Option<String>,
    #[serde(default)]
    pub visibility: Option<String>,
    #[serde(default)]
    pub source_kind: Option<String>,
    #[serde(default)]
    pub share_url: Option<String>,
    /// Canonical public report URL on the webapp, built server-side from
    /// `public_base_url` — the client need not know the webapp origin (which
    /// differs from the API origin in local dev). Absent on older servers.
    #[serde(default)]
    pub report_url: Option<String>,
    #[serde(default)]
    pub expires_at: Option<String>,
}

/// `GET /api/v1/scans/cli-challenge` — a stateless Proof-of-Work challenge for
/// the CLI scan-submit gate (D-05-30). `status` of a submit stays `String` so an
/// unknown value never panics.
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ChallengeResponse {
    pub challenge: String,
    pub difficulty: u32,
    #[serde(default)]
    pub expires_at: Option<String>,
}

/// 202 result of `POST /api/v1/scans` (a GitHub-URL submit).
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ScanSubmitResponse {
    pub id: String,
    /// Free-form so an unknown status never breaks deserialization.
    pub status: String,
    #[serde(default)]
    pub cached: bool,
    #[serde(default)]
    pub rubric_version: Option<String>,
    /// Present (non-null) only for an `unlisted` submission.
    #[serde(default)]
    pub share_url: Option<String>,
}

/// 202 result of `POST /api/v1/scans/upload` (a local-content submit).
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ScanUploadResponse {
    pub id: String,
    pub status: String,
    #[serde(default)]
    pub source_kind: Option<String>,
    #[serde(default)]
    pub visibility: Option<String>,
    #[serde(default)]
    pub slug: Option<String>,
    /// Present (non-null) only for an `unlisted` upload.
    #[serde(default)]
    pub share_url: Option<String>,
}

/// `GET /health`.
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct HealthResponse {
    pub status: String,
    pub version: String,
    pub git_sha: String,
    #[serde(default)]
    pub migrations_ok: bool,
    #[serde(default)]
    pub migrations_error: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn severity_deserializes_lowercase() {
        let s: Severity = serde_json::from_str("\"critical\"").unwrap();
        assert_eq!(s, Severity::Critical);
    }

    #[test]
    fn unknown_severity_falls_through() {
        let s: Severity = serde_json::from_str("\"apocalyptic\"").unwrap();
        assert_eq!(s, Severity::Unknown);
        assert_eq!(s.rank(), 0);
    }

    #[test]
    fn unknown_tier_falls_through() {
        let t: Tier = serde_json::from_str("\"plaid\"").unwrap();
        assert_eq!(t, Tier::Unknown);
    }

    #[test]
    fn severity_rank_orders_correctly() {
        assert!(Severity::Critical.rank() > Severity::High.rank());
        assert!(Severity::High.rank() > Severity::Low.rank());
        assert_eq!(Severity::Info.rank(), 0);
    }

    #[test]
    fn list_envelope_uses_data_key() {
        let json = r#"{"data":[],"total_count":0,"page":1,"total_pages":0,"page_size":24}"#;
        let env: CatalogListEnvelope = serde_json::from_str(json).unwrap();
        assert_eq!(env.total_count, 0);
        assert!(env.data.is_empty());
    }

    #[test]
    fn evidence_excerpt_hit_line() {
        let json = r#"{"file":"a.py","lines":[{"line_no":1,"text":"ok","hit":false},{"line_no":2,"text":"BAD","hit":true}],"truncated":false}"#;
        let ex: EvidenceExcerpt = serde_json::from_str(json).unwrap();
        assert_eq!(ex.hit_line().unwrap().line_no, 2);
        assert_eq!(ex.hit_line().unwrap().text, "BAD");
    }

    #[test]
    fn unknown_object_keys_are_ignored() {
        // The API's CatalogItemDetail is a superset of CatalogItemSummary;
        // extra keys must not break deserialization.
        let json = r#"{"id":"x","slug":"a--b--skill-c","kind":"skill","display_name":"C","popularity_tier":"emerging","item_metadata":{"z":1},"sources":[]}"#;
        let item: CatalogItemSummary = serde_json::from_str(json).unwrap();
        assert_eq!(item.slug, "a--b--skill-c");
    }
}
