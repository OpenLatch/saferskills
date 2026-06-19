//! `.agentscanignore` baseline filtering for `agent`.
//!
//! A gitleaks-style, committed allowlist of known/accepted agent-scan findings.
//! One fingerprint per line: `<test_id>:<leaked_canary_slot|"*"> # reason`. A `*`
//! slot matches any leak of that test; a concrete slot matches only that leak. The
//! `--baseline <prior-report.json>` form instead derives the fingerprint set from a
//! prior report's findings (suppress anything already seen). Suppressed findings are
//! counted but never drive `--fail-on`.

use std::collections::BTreeSet;
use std::path::Path;

use crate::api::dto::AgentFindingDto;
use crate::core::error::{SsError, ERR_SCAN_TARGET};

/// One baseline fingerprint. `slot == None` is the `*` wildcard (any leak of the
/// test); `slot == Some(s)` matches only that leaked-canary slot.
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub struct Fingerprint {
    pub test_id: String,
    pub slot: Option<String>,
}

impl Fingerprint {
    /// Whether this fingerprint suppresses `finding`.
    fn matches(&self, finding: &AgentFindingDto) -> bool {
        if self.test_id != finding.test_id {
            return false;
        }
        match &self.slot {
            None => true, // `*` wildcard
            Some(slot) => finding.leaked_canary_slot.as_deref() == Some(slot.as_str()),
        }
    }
}

/// Parse `.agentscanignore` text into a fingerprint set. `#`-comments (whole-line
/// and inline) + blank lines are skipped. A malformed line (no `:`) is an error.
pub fn parse(text: &str) -> Result<BTreeSet<Fingerprint>, SsError> {
    let mut out = BTreeSet::new();
    for (n, raw) in text.lines().enumerate() {
        // Strip an inline `# reason` comment, then trim.
        let line = raw.split('#').next().unwrap_or("").trim();
        if line.is_empty() {
            continue;
        }
        let (test_id, slot) = line.split_once(':').ok_or_else(|| {
            SsError::new(
                ERR_SCAN_TARGET,
                format!(
                    "Invalid .agentscanignore line {}: expected `<test_id>:<slot|*>`.",
                    n + 1
                ),
            )
        })?;
        let test_id = test_id.trim().to_string();
        let slot = match slot.trim() {
            "*" | "" => None,
            s => Some(s.to_string()),
        };
        out.insert(Fingerprint { test_id, slot });
    }
    Ok(out)
}

/// Load + parse a `.agentscanignore` file.
pub fn load(path: &Path) -> Result<BTreeSet<Fingerprint>, SsError> {
    let text = std::fs::read_to_string(path).map_err(|e| {
        SsError::new(
            ERR_SCAN_TARGET,
            format!("Cannot read baseline {}: {e}", path.display()),
        )
    })?;
    parse(&text)
}

/// Derive a fingerprint set from a prior report's findings (`--baseline X.json`):
/// suppress anything already present (exact test_id + slot).
pub fn from_findings(findings: &[AgentFindingDto]) -> BTreeSet<Fingerprint> {
    findings
        .iter()
        .map(|f| Fingerprint {
            test_id: f.test_id.clone(),
            slot: f.leaked_canary_slot.clone(),
        })
        .collect()
}

/// Partition findings into `(kept, suppressed)` against a baseline. A finding is
/// suppressed when ANY fingerprint matches it.
pub fn filter(
    findings: Vec<AgentFindingDto>,
    baseline: &BTreeSet<Fingerprint>,
) -> (Vec<AgentFindingDto>, Vec<AgentFindingDto>) {
    let mut kept = Vec::new();
    let mut suppressed = Vec::new();
    for f in findings {
        if baseline.iter().any(|fp| fp.matches(&f)) {
            suppressed.push(f);
        } else {
            kept.push(f);
        }
    }
    (kept, suppressed)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::api::dto::{AgentRemediation, Severity};

    fn finding(test_id: &str, slot: Option<&str>) -> AgentFindingDto {
        AgentFindingDto {
            id: "f".into(),
            test_id: test_id.into(),
            severity: Severity::High,
            verdict: "vulnerable".into(),
            family: "fam".into(),
            owasp_refs: vec![],
            atlas_refs: vec![],
            nist_refs: vec![],
            score_delta: -25,
            detection_rule: "substring".into(),
            leaked_canary_slot: slot.map(String::from),
            title: "t".into(),
            explanation: "e".into(),
            severity_rationale: None,
            category_label: None,
            remediation: AgentRemediation {
                action: "fix".into(),
                steps: None,
                safer_pattern: None,
            },
            evidence_excerpt: None,
        }
    }

    #[test]
    fn parse_skips_comments_and_blanks() {
        let text = "# header\n\nAS-06:*  # accepted\nAS-12:AS-12\n";
        let set = parse(text).unwrap();
        assert_eq!(set.len(), 2);
        assert!(set.contains(&Fingerprint {
            test_id: "AS-06".into(),
            slot: None
        }));
        assert!(set.contains(&Fingerprint {
            test_id: "AS-12".into(),
            slot: Some("AS-12".into())
        }));
    }

    #[test]
    fn parse_rejects_malformed_line() {
        assert!(parse("AS-06\n").is_err());
    }

    #[test]
    fn wildcard_matches_any_slot() {
        let base = parse("AS-06:*\n").unwrap();
        let (kept, sup) = filter(
            vec![finding("AS-06", Some("AS-06")), finding("AS-01", None)],
            &base,
        );
        assert_eq!(kept.len(), 1);
        assert_eq!(kept[0].test_id, "AS-01");
        assert_eq!(sup.len(), 1);
    }

    #[test]
    fn concrete_slot_matches_only_that_slot() {
        let base = parse("AS-06:AS-06\n").unwrap();
        let (kept, sup) = filter(
            vec![
                finding("AS-06", Some("AS-06")),
                finding("AS-06", Some("other")),
            ],
            &base,
        );
        assert_eq!(sup.len(), 1);
        assert_eq!(kept.len(), 1);
        assert_eq!(kept[0].leaked_canary_slot.as_deref(), Some("other"));
    }

    #[test]
    fn from_findings_round_trips() {
        let base = from_findings(&[finding("AS-06", Some("AS-06"))]);
        let (kept, sup) = filter(vec![finding("AS-06", Some("AS-06"))], &base);
        assert!(kept.is_empty());
        assert_eq!(sup.len(), 1);
    }
}
