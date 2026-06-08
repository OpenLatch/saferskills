//! `saferskills info <name>` (alias `check`) — the unblocked read headline
//! (D-05-18). Resolves the typed name, fetches the item detail, and renders
//! the score + tier + ranked findings + report URL. No auth, no captcha.

use super::report;
use crate::api::dto::{FindingResponse, ItemDetailResponse, Tier};
use crate::api::Api;
use crate::cli::color;
use crate::cli::output::OutputConfig;
use crate::cli::InfoArgs;
use crate::core::config::Config;
use crate::core::error::SsError;

/// Run `info`.
pub async fn run_info(args: &InfoArgs, output: &OutputConfig) -> Result<(), SsError> {
    let config = Config::load()?;
    let api = Api::new(config.api_base(None))?;

    let spinner = output.create_spinner(&format!("Resolving {}…", args.name));
    let summary = match api.resolve(&args.name).await {
        Ok(s) => s,
        Err(e) => {
            if let Some(pb) = spinner {
                pb.finish_and_clear();
            }
            return Err(e);
        }
    };
    let detail = api.get_item(&summary.slug).await;
    if let Some(pb) = spinner {
        pb.finish_and_clear();
    }
    let detail = detail?;

    let report_url = format!("{}/items/{}", api.base(), detail.item.slug);

    if output.is_json() {
        output.print_json(&trimmed(&detail, &report_url));
        return Ok(());
    }

    render_human(output, &detail, &report_url);
    Ok(())
}

/// Score + tier from the item summary, falling back to the latest scan.
fn score_and_tier(detail: &ItemDetailResponse) -> (Option<u8>, Tier) {
    let score = detail
        .item
        .latest_scan_score
        .or_else(|| detail.latest_scan.as_ref().map(|s| s.aggregate_score));
    let tier = detail
        .item
        .latest_scan_tier
        .or_else(|| detail.latest_scan.as_ref().map(|s| s.tier))
        .unwrap_or(Tier::Unscoped);
    (score, tier)
}

/// Findings, highest-severity first.
fn ranked_findings(detail: &ItemDetailResponse) -> Vec<&FindingResponse> {
    let mut findings: Vec<&FindingResponse> = detail
        .latest_scan
        .as_ref()
        .map(|s| s.findings.iter().collect())
        .unwrap_or_default();
    findings.sort_by_key(|f| std::cmp::Reverse(f.severity.rank()));
    findings
}

fn render_human(output: &OutputConfig, detail: &ItemDetailResponse, report_url: &str) {
    let c = output.color;
    let (score, tier) = score_and_tier(detail);
    let name = color::bold(&detail.item.display_name, c);
    output.print_info(&format!("{name}  {}", color::dim(&detail.item.kind, c)));

    let score_str = score
        .map(|v| format!("{v}/100"))
        .unwrap_or_else(|| "—".to_string());
    output.print_info(&format!("{}  {score_str}", color::tier_dot(tier, c)));

    // ── never-scanned items: don't imply "clean" with a green "No findings" ──
    // A catalog item with no `latest_scan` was never scored; mirror `list`'s
    // explicit "○ not scanned" state and point at a scan instead.
    let Some(scan) = detail.latest_scan.as_ref() else {
        output.print_info("");
        output.print_info(&color::dim("\u{25cb} Not scanned yet.", c));
        if let Some(url) = detail.item.github_url.as_deref() {
            output.print_substep(&format!("Scan it now: saferskills scan {url}"));
        }
        output.print_info("");
        output.print_info(&format!("Report: {report_url}"));
        return;
    };

    // ── category breakdown (single capability — no "mean across" suffix) ──
    if !scan.sub_scores.is_empty() {
        output.print_info("");
        output.print_info(&color::bold("Category breakdown", c));
        report::print_axes(output, &scan.sub_scores, 4);
    }

    // ── all findings, every severity, uncapped ──
    let findings = ranked_findings(detail);
    if findings.is_empty() {
        output.print_info("");
        output.print_info(&format!("{} No findings.", color::checkmark(c)));
    } else {
        output.print_info("");
        output.print_info(&format!("{} finding(s):", findings.len()));
        for f in &findings {
            report::print_finding_row(output, f, None, output.verbose, true);
        }
    }

    output.print_info("");
    output.print_info(&format!("Report: {report_url}"));
}

/// The trimmed, jq-friendly JSON payload for `--json`.
fn trimmed(detail: &ItemDetailResponse, report_url: &str) -> serde_json::Value {
    let (score, tier) = score_and_tier(detail);
    let findings: Vec<serde_json::Value> = ranked_findings(detail)
        .iter()
        .map(|f| {
            serde_json::json!({
                "rule_id": f.rule_id,
                "severity": f.severity,
                "file_path": f.file_path,
                "line_start": f.line_start,
                "line_end": f.line_end,
                "remediation_link": f.remediation_link,
                "evidence": f.evidence_excerpt.as_ref().and_then(|e| e.hit_line()).map(|l| &l.text),
            })
        })
        .collect();
    serde_json::json!({
        "slug": detail.item.slug,
        "name": detail.item.display_name,
        "kind": detail.item.kind,
        "score": score,
        "tier": tier,
        "report_url": report_url,
        "sub_scores": detail.latest_scan.as_ref().map(|s| &s.sub_scores),
        "findings": findings,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::api::dto::{CatalogItemSummary, Severity};

    fn detail_with(score: Option<u8>, tier: Option<Tier>, sevs: &[Severity]) -> ItemDetailResponse {
        let findings = sevs
            .iter()
            .enumerate()
            .map(|(i, s)| FindingResponse {
                id: format!("f{i}"),
                rule_id: format!("SS-MCP-RULE-0{i}"),
                severity: *s,
                sub_score: "security".into(),
                penalty: 10,
                status_at_scan: "active".into(),
                file_path: "src/x.ts".into(),
                line_start: 1,
                line_end: None,
                matched_content_sha256: "0".repeat(64),
                remediation_link: "https://x".into(),
                rubric_version: "abc1234".into(),
                evidence_excerpt: None,
                title: None,
                explanation: None,
                category_label: None,
                severity_rationale: None,
                remediation: None,
            })
            .collect();
        ItemDetailResponse {
            item: CatalogItemSummary {
                id: "id".into(),
                slug: "a--b--mcp-server-x".into(),
                kind: "mcp_server".into(),
                display_name: "X".into(),
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
                findings_count: sevs.len() as i64,
                registries: vec![],
                agent_compatibility: vec![],
                updated_at: None,
            },
            latest_scan: Some(crate::api::dto::ScanReportDetail {
                id: "s".into(),
                github_url: None,
                slug: "a--b--mcp-server-x".into(),
                display_name: "X".into(),
                aggregate_score: score.unwrap_or(0),
                tier: tier.unwrap_or(Tier::Unscoped),
                sub_scores: Default::default(),
                findings,
                scanned_at: None,
                rubric_version: None,
                engine_version: None,
                component_path: None,
                scan_run_id: None,
            }),
        }
    }

    #[test]
    fn findings_ranked_highest_severity_first() {
        let d = detail_with(
            Some(60),
            Some(Tier::Yellow),
            &[Severity::Low, Severity::Critical, Severity::Medium],
        );
        let ranked = ranked_findings(&d);
        assert_eq!(ranked[0].severity, Severity::Critical);
        assert_eq!(ranked[2].severity, Severity::Low);
    }

    #[test]
    fn score_falls_back_to_latest_scan() {
        let d = detail_with(None, None, &[]);
        let (score, tier) = score_and_tier(&d);
        assert_eq!(score, Some(0));
        assert_eq!(tier, Tier::Unscoped);
    }

    #[test]
    fn trimmed_json_shape() {
        let d = detail_with(Some(87), Some(Tier::Green), &[Severity::High]);
        let v = trimmed(&d, "https://saferskills.ai/items/a--b--mcp-server-x");
        assert_eq!(v["score"], 87);
        assert_eq!(v["tier"], "green");
        assert_eq!(
            v["report_url"],
            "https://saferskills.ai/items/a--b--mcp-server-x"
        );
        assert_eq!(v["findings"].as_array().unwrap().len(), 1);
        assert_eq!(v["findings"][0]["severity"], "high");
    }

    fn out(verbose: bool, color: bool) -> OutputConfig {
        OutputConfig {
            format: crate::cli::output::OutputFormat::Human,
            verbose,
            quiet: false,
            color,
        }
    }

    #[test]
    fn render_human_covers_evidence_and_range() {
        // Verbose + color + an evidence excerpt + a multi-line range + a
        // remediation action (exercises the `show_remediation` branch).
        let mut d = detail_with(Some(72), Some(Tier::Yellow), &[Severity::High]);
        if let Some(scan) = d.latest_scan.as_mut() {
            scan.findings[0].line_end = Some(3);
            scan.findings[0].remediation = Some(crate::api::dto::FindingRemediation {
                action: "Remove the dangerous call".into(),
                steps: None,
                safer_pattern: None,
            });
            scan.findings[0].evidence_excerpt = Some(crate::api::dto::EvidenceExcerpt {
                file: "src/x.ts".into(),
                lang: None,
                lines: vec![crate::api::dto::EvidenceLine {
                    line_no: 1,
                    text: "bad();".into(),
                    hit: true,
                }],
                truncated: false,
            });
        }
        render_human(&out(true, true), &d, "https://x/items/y");
    }

    #[test]
    fn render_human_covers_all_findings_and_empty() {
        // Many findings → all rendered (uncapped), no truncation line.
        let many = [Severity::High; 7];
        let d = detail_with(Some(40), Some(Tier::Orange), &many);
        render_human(&out(false, false), &d, "https://x/items/y");
        // No findings → the "No findings." path.
        let empty = detail_with(Some(95), Some(Tier::Green), &[]);
        render_human(&out(false, true), &empty, "https://x/items/z");
    }

    #[test]
    fn render_human_shows_category_breakdown() {
        // All 5 axes populated → the Category breakdown block renders (color on/off).
        let mut d = detail_with(Some(60), Some(Tier::Yellow), &[Severity::Medium]);
        if let Some(scan) = d.latest_scan.as_mut() {
            for (key, _) in color::AXES {
                scan.sub_scores.insert(key.to_string(), 70);
            }
        }
        render_human(&out(false, false), &d, "https://x/items/y");
        render_human(&out(false, true), &d, "https://x/items/y");
    }

    #[test]
    fn render_human_lists_all_findings_uncapped() {
        // ≥7 mixed-severity findings, non-verbose → every one is rendered.
        let d = detail_with(
            Some(35),
            Some(Tier::Red),
            &[
                Severity::Critical,
                Severity::High,
                Severity::High,
                Severity::Medium,
                Severity::Medium,
                Severity::Low,
                Severity::Info,
            ],
        );
        assert_eq!(ranked_findings(&d).len(), 7);
        render_human(&out(false, false), &d, "https://x/items/y");
    }

    #[test]
    fn render_human_handles_never_scanned_item() {
        // A catalog item with no `latest_scan` (never scored) must render the
        // "○ Not scanned yet" state + a scan hint, NOT a green "No findings".
        let mut d = detail_with(None, None, &[]);
        d.latest_scan = None;
        d.item.github_url = Some("https://github.com/acme/thing".into());
        render_human(&out(false, false), &d, "https://x/items/y");
        render_human(&out(false, true), &d, "https://x/items/y");
    }

    #[test]
    fn trimmed_json_includes_sub_scores() {
        let mut d = detail_with(Some(80), Some(Tier::Green), &[Severity::Low]);
        if let Some(scan) = d.latest_scan.as_mut() {
            scan.sub_scores.insert("security".into(), 88);
        }
        let v = trimmed(&d, "https://x/items/y");
        assert_eq!(v["sub_scores"]["security"], 88);
    }
}
