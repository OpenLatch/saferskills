//! Shared audit-report renderers + pure helpers used by both `capability` (multi-
//! capability run report) and `info` (single-capability report). Lifted out of
//! `capability.rs` so the two surfaces stay byte-for-byte visually consistent — no
//! copy/paste. The multi-capability glue (`category_means`, agents section,
//! worst-first list, `top_findings`, …) stays in `scan.rs`.

use std::collections::BTreeMap;

use crate::api::dto::{FindingResponse, Severity};
use crate::cli::color;
use crate::cli::output::OutputConfig;

// ─── formatting helpers ──────────────────────────────────────────────────────

/// Right-pad a plain (uncolored) string to `width` display columns.
pub(crate) fn pad(s: &str, width: usize) -> String {
    let n = s.chars().count();
    if n >= width {
        s.to_string()
    } else {
        format!("{s}{}", " ".repeat(width - n))
    }
}

/// Left-pad a small number to `width` columns.
pub(crate) fn pad_left(n: u8, width: usize) -> String {
    let s = n.to_string();
    let len = s.len();
    if len >= width {
        s
    } else {
        format!("{}{s}", " ".repeat(width - len))
    }
}

// ─── severity / finding helpers (pure) ───────────────────────────────────────

pub(crate) fn severity_str(sev: Severity) -> &'static str {
    match sev {
        Severity::Critical => "critical",
        Severity::High => "high",
        Severity::Medium => "medium",
        Severity::Low => "low",
        Severity::Info => "info",
        Severity::Unknown => "unknown",
    }
}

pub(crate) fn worst_severity(findings: &[FindingResponse]) -> Option<Severity> {
    findings.iter().map(|f| f.severity).max_by_key(|s| s.rank())
}

/// A short finding rollup chip, mirroring the webapp's clear/high/warn classes.
pub(crate) fn finding_rollup(findings: &[FindingResponse]) -> String {
    let total = findings.len();
    if total == 0 {
        return "all clear".to_string();
    }
    let crit = findings
        .iter()
        .filter(|f| f.severity == Severity::Critical)
        .count();
    let high = findings
        .iter()
        .filter(|f| f.severity == Severity::High)
        .count();
    let med = findings
        .iter()
        .filter(|f| f.severity == Severity::Medium)
        .count();
    let low = findings
        .iter()
        .filter(|f| f.severity == Severity::Low)
        .count();
    if crit > 0 {
        format!("{crit} critical · {total} findings")
    } else if high > 0 {
        format!("{high} high · {total} findings")
    } else if med > 0 {
        format!("{med} medium")
    } else if low > 0 {
        format!("{low} low")
    } else {
        format!("{total} findings")
    }
}

pub(crate) fn kind_label(kind: &str) -> &str {
    match kind {
        "skill" => "Skill",
        "mcp_server" => "MCP",
        "hook" => "Hook",
        "plugin" => "Plugin",
        "rules" => "Rules",
        other => other,
    }
}

// ─── shared renderers ────────────────────────────────────────────────────────

/// Render the 5 scoring axes as labeled bar gauges off a plain `sub_scores` map.
/// `indent` is the leading-space width (scan's nested rows use 8, info uses 4).
/// Only axes present in the map are shown, in fixed [`color::AXES`] order.
pub(crate) fn print_axes(output: &OutputConfig, sub_scores: &BTreeMap<String, i64>, indent: usize) {
    let c = output.color;
    let spaces = " ".repeat(indent);
    for (key, label) in color::AXES {
        if let Some(v) = sub_scores.get(key) {
            output.print_info(&format!(
                "{spaces}{}  {}  {v}",
                pad(label, 13),
                color::bar_gauge((*v).clamp(0, 100) as u8, 10, c),
            ));
        }
    }
}

/// Render one finding row in the audit-report style: a severity badge + title
/// line, then a dim meta line (rule_id + optional capability + location), then
/// (opt-in) a dim remediation action and a dim verbatim evidence line.
///
/// `context` is the capability name (scan's multi-cap list) or `None` (info's
/// single capability, which then uses its line-range location format).
/// `show_remediation` adds the `→ action` line; `show_evidence` adds the matched
/// evidence line (info passes `true`, scan `false`).
pub(crate) fn print_finding_row(
    output: &OutputConfig,
    f: &FindingResponse,
    context: Option<&str>,
    show_remediation: bool,
    show_evidence: bool,
) {
    let c = output.color;
    let title = f.title.clone().unwrap_or_else(|| f.rule_id.clone());
    output.print_info(&format!(
        "    {}  {title}",
        color::severity_badge(f.severity, c)
    ));

    let meta = match context {
        Some(cap) => format!("{} · {cap} · {}:{}", f.rule_id, f.file_path, f.line_start),
        None => {
            let loc = match f.line_end {
                Some(end) if end != f.line_start => {
                    format!("{}:{}-{}", f.file_path, f.line_start, end)
                }
                _ => format!("{}:{}", f.file_path, f.line_start),
            };
            format!("{} · {loc}", f.rule_id)
        }
    };
    output.print_info(&format!("                {}", color::dim(&meta, c)));

    if show_remediation {
        if let Some(rem) = &f.remediation {
            output.print_info(&format!(
                "                {}",
                color::dim(&format!("→ {}", rem.action), c)
            ));
        }
    }
    if show_evidence {
        if let Some(line) = f.evidence_excerpt.as_ref().and_then(|e| e.hit_line()) {
            output.print_info(&format!(
                "                {}",
                color::dim(line.text.trim_end(), c)
            ));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::api::dto::{EvidenceExcerpt, EvidenceLine, FindingRemediation};
    use crate::cli::output::OutputFormat;

    fn out_plain() -> OutputConfig {
        OutputConfig {
            format: OutputFormat::Human,
            verbose: false,
            quiet: false,
            color: false,
        }
    }

    fn finding(rule: &str, sev: Severity, title: &str, file: &str, line: u32) -> FindingResponse {
        FindingResponse {
            id: "f".into(),
            rule_id: rule.into(),
            severity: sev,
            sub_score: "security".into(),
            penalty: 0,
            status_at_scan: "active".into(),
            file_path: file.into(),
            line_start: line,
            line_end: None,
            matched_content_sha256: "x".into(),
            remediation_link: "".into(),
            rubric_version: "v3".into(),
            evidence_excerpt: None,
            title: Some(title.into()),
            explanation: None,
            category_label: None,
            severity_rationale: None,
            remediation: None,
        }
    }

    #[test]
    fn finding_rollup_chips() {
        assert_eq!(finding_rollup(&[]), "all clear");
        let crit = vec![
            finding("R1", Severity::Critical, "t", "a", 1),
            finding("R2", Severity::Low, "t", "a", 2),
            finding("R3", Severity::Low, "t", "a", 3),
        ];
        assert_eq!(finding_rollup(&crit), "1 critical · 3 findings");
        let med = vec![finding("R", Severity::Medium, "t", "a", 1)];
        assert_eq!(finding_rollup(&med), "1 medium");
    }

    #[test]
    fn print_axes_renders_present_axes_only() {
        // Only `security` + `community` present → the other three axes are skipped,
        // and the renderer must not panic with color on or off.
        let mut sub = BTreeMap::new();
        sub.insert("security".to_string(), 72i64);
        sub.insert("community".to_string(), 40i64);
        print_axes(&out_plain(), &sub, 4);
        let mut color_out = out_plain();
        color_out.color = true;
        print_axes(&color_out, &sub, 8);
    }

    #[test]
    fn print_finding_row_context_and_remediation() {
        let mut f = finding("SS-X-01", Severity::High, "Bad thing", "src/x.ts", 12);
        f.line_end = Some(15);
        f.remediation = Some(FindingRemediation {
            action: "Stop doing the bad thing".into(),
            steps: None,
            safer_pattern: None,
        });
        f.evidence_excerpt = Some(EvidenceExcerpt {
            file: "src/x.ts".into(),
            lang: None,
            lines: vec![EvidenceLine {
                line_no: 12,
                text: "  bad();  ".into(),
                hit: true,
            }],
            truncated: false,
        });
        // Some(context), no remediation/evidence (scan's call shape).
        print_finding_row(&out_plain(), &f, Some("pdf-extract"), false, false);
        // None context (info's line-range location) + remediation + evidence.
        print_finding_row(&out_plain(), &f, None, true, true);
        // remediation requested but absent → no `→` line, must not panic.
        let bare = finding("SS-Y-02", Severity::Low, "Minor", "a.py", 3);
        print_finding_row(&out_plain(), &bare, None, true, true);
    }

    #[test]
    fn severity_str_maps_all_tiers() {
        assert_eq!(severity_str(Severity::Critical), "critical");
        assert_eq!(severity_str(Severity::Info), "info");
        assert_eq!(severity_str(Severity::Unknown), "unknown");
    }

    #[test]
    fn worst_severity_picks_highest() {
        let fs = vec![
            finding("R1", Severity::Low, "t", "a", 1),
            finding("R2", Severity::Critical, "t", "a", 2),
            finding("R3", Severity::Medium, "t", "a", 3),
        ];
        assert_eq!(worst_severity(&fs), Some(Severity::Critical));
        assert_eq!(worst_severity(&[]), None);
    }

    #[test]
    fn pad_and_pad_left() {
        assert_eq!(pad("ab", 5), "ab   ");
        assert_eq!(pad("abcdef", 3), "abcdef");
        assert_eq!(pad_left(7, 3), "  7");
        assert_eq!(pad_left(100, 2), "100");
    }

    #[test]
    fn kind_label_maps() {
        assert_eq!(kind_label("mcp_server"), "MCP");
        assert_eq!(kind_label("skill"), "Skill");
        assert_eq!(kind_label("other"), "other");
    }
}
