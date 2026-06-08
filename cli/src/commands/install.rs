//! `saferskills install <name>` — the cross-ecosystem wedge (D-05-18..25).
//!
//! Flow: detect agents → select (multi-select pre-checked / `--to` / `--all`) →
//! resolve + re-verify the score (+ `--seen-score` drift) → conflict check →
//! the §5.5 severity gate → per-agent writer install with record-then-write +
//! LIFO rollback (D-05-24) → registry row → anonymous install report (D-05-31).

use std::io::IsTerminal;

use serde_json::{json, Value};

use crate::agents::writer::{ResolvedItem, VerifyStatus};
use crate::agents::{detect_all, no_agents_error, writers, AgentId, DetectedAgent, Scope};
use crate::api::dto::{CatalogItemSummary, FindingResponse, ItemDetailResponse, Severity, Tier};
use crate::api::Api;
use crate::cli::output::OutputConfig;
use crate::cli::{InstallArgs, Interaction};
use crate::core::config::Config;
use crate::core::error::{
    SsError, ERR_CONFLICT, ERR_GATE_CANCELLED, ERR_NEEDS_FLAG, ERR_WRITER_UNSUPPORTED,
    ERR_WRITE_ROLLBACK,
};
use crate::core::registry::{self, InstallChange, InstallRecord};
use crate::core::telemetry;

/// Run `install`.
pub async fn run_install(
    args: &InstallArgs,
    inter: Interaction,
    output: &OutputConfig,
) -> Result<(), SsError> {
    let config = Config::load()?;
    let api = Api::new(config.api_base(None))?;
    let scope = if args.project {
        Scope::Project
    } else {
        Scope::Global
    };

    // 1. Detect agents.
    let detected = detect_all(scope);
    if detected.is_empty() {
        return Err(no_agents_error());
    }

    // 2. Resolve + re-verify the score (never page-cached, CLI-2).
    let summary = api.resolve(&args.name).await?;
    let detail = api.get_item(&summary.slug).await?;
    let (score, tier) = score_and_tier(&detail);
    let findings = ranked_findings(&detail);

    // 3. Targeting: detected ∩ item.agent_compatibility ∩ writer-supports(kind).
    let kind = detail.item.kind.clone();
    let selectable = selectable_agents(&detected, &detail.item, &kind);
    if selectable.is_empty() {
        return Err(SsError::new(
            ERR_WRITER_UNSUPPORTED,
            format!(
                "No detected agent can install this {kind}. Compatible: {}.",
                detail.item.agent_compatibility.join(", ")
            ),
        ));
    }

    // 4. Agent selection (D-05-20).
    let chosen = select_agents(args, inter, output, &selectable)?;

    // 5. Drift re-prompt (D-05-25) + severity gate (D-05-19).
    surface_score(output, &detail, score, tier);
    drift_reprompt(output, inter, args.seen_score, score, &findings)?;

    // Finding prose is inlined on the report findings (D-05-32 reversed) — no
    // rule-corpus fetch; the gate renders straight from each finding.
    apply_severity_gate(output, inter, &config, &detail.item, &findings)?;

    // 6. Conflict (D-05-22).
    let mut records = registry::load()?;
    if let Some(idx) = records.iter().position(|r| r.slug == summary.slug) {
        resolve_conflict(args, inter, output, &mut records, idx)?;
    }

    // 7. Build the resolved item (downloads the skill zip if needed).
    let resolved = build_resolved_item(&api, &detail.item, &kind, output).await?;

    if args.dry_run {
        return print_plan(output, &chosen, &resolved);
    }

    // 8. Record-then-write across agents, rolling back on any failure (D-05-24).
    let applied = install_to_agents(output, &chosen, &resolved)?;

    // 9. Registry row (written only after all agents succeeded).
    let record = InstallRecord {
        canonical_id: detail.item.id.clone(),
        slug: summary.slug.clone(),
        name: detail.item.display_name.clone(),
        kind: kind.clone(),
        version: detail
            .latest_scan
            .as_ref()
            .and_then(|s| s.scanned_at.clone()),
        agents: chosen.iter().map(|a| a.id.as_str().to_string()).collect(),
        changes: applied.clone(),
        installed_at: chrono::Utc::now(),
        seen_score: score,
    };
    records.retain(|r| r.slug != record.slug);
    records.push(record);
    registry::save(&records)?;

    // 10. Install report — unconditional + fail-open (no consent; kill-switch only).
    maybe_report(&api, &summary.slug, &chosen, &kind).await;

    success_screen(output, &summary);

    if output.is_json() {
        output.print_json(&json!({
            "installed": chosen.iter().map(|a| a.id.as_str()).collect::<Vec<_>>(),
            "slug": summary.slug,
            "score": score,
            "tier": tier,
            "findings": findings.len(),
            "changes": applied.len(),
        }));
    }
    Ok(())
}

// ─── score / findings helpers ────────────────────────────────────────────────

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

fn ranked_findings(detail: &ItemDetailResponse) -> Vec<FindingResponse> {
    let mut f: Vec<FindingResponse> = detail
        .latest_scan
        .as_ref()
        .map(|s| s.findings.clone())
        .unwrap_or_default();
    f.sort_by_key(|f| std::cmp::Reverse(f.severity.rank()));
    f
}

fn highest_severity(findings: &[FindingResponse]) -> Option<Severity> {
    findings.iter().map(|f| f.severity).max_by_key(|s| s.rank())
}

// ─── agent targeting + selection (D-05-20) ───────────────────────────────────

/// detected ∩ item.agent_compatibility ∩ writer-supports(kind).
fn selectable_agents(
    detected: &[DetectedAgent],
    item: &CatalogItemSummary,
    kind: &str,
) -> Vec<DetectedAgent> {
    detected
        .iter()
        .filter(|a| item.agent_compatibility.iter().any(|c| c == a.id.as_str()))
        .filter(|a| writers::writer_for(a.id).supports_kind(kind, a))
        .cloned()
        .collect()
}

fn can_prompt(inter: Interaction, output: &OutputConfig) -> bool {
    !inter.non_interactive
        && !output.is_json()
        && !output.is_quiet()
        && std::io::stderr().is_terminal()
}

fn select_agents(
    args: &InstallArgs,
    inter: Interaction,
    output: &OutputConfig,
    selectable: &[DetectedAgent],
) -> Result<Vec<DetectedAgent>, SsError> {
    for a in selectable {
        output.print_step(&format!("{} detected", a.id.display_name()));
    }

    // Explicit --to wins (warn + canonicalize legacy ids).
    if !args.to.is_empty() {
        let mut chosen = Vec::new();
        for raw in &args.to {
            let (id, warning) = AgentId::parse_cli(raw)?;
            if let Some(w) = warning {
                output.print_warn(&w);
            }
            match selectable.iter().find(|a| a.id == id) {
                Some(a) => chosen.push(a.clone()),
                None => {
                    return Err(SsError::new(
                        ERR_WRITER_UNSUPPORTED,
                        format!(
                            "{} is not detected or not compatible here.",
                            id.display_name()
                        ),
                    ))
                }
            }
        }
        return Ok(chosen);
    }

    if args.all {
        return Ok(selectable.to_vec());
    }

    // Interactive multi-select (all pre-checked). Non-interactive → name the flag.
    if !can_prompt(inter, output) {
        return Err(SsError::new(
            ERR_NEEDS_FLAG,
            "Multiple agents detected and no selection given.",
        )
        .with_suggestion("Pass --to <agent> (repeatable) or --all to choose non-interactively.")
        .with_exit_code(2));
    }

    let labels: Vec<String> = selectable
        .iter()
        .map(|a| a.id.display_name().to_string())
        .collect();
    let defaults: Vec<usize> = (0..labels.len()).collect();
    let picked = inquire::MultiSelect::new("Install to which agents?", labels.clone())
        .with_default(&defaults)
        .prompt()
        .map_err(|_| SsError::new(ERR_GATE_CANCELLED, "Install cancelled."))?;
    let chosen: Vec<DetectedAgent> = selectable
        .iter()
        .zip(labels.iter())
        .filter(|(_, label)| picked.contains(label))
        .map(|(a, _)| a.clone())
        .collect();
    if chosen.is_empty() {
        return Err(SsError::new(
            ERR_GATE_CANCELLED,
            "No agents selected — nothing to install.",
        ));
    }
    Ok(chosen)
}

// ─── score surface + drift re-prompt (D-05-25) ───────────────────────────────

fn surface_score(
    output: &OutputConfig,
    detail: &ItemDetailResponse,
    score: Option<u8>,
    tier: Tier,
) {
    if output.is_json() {
        return;
    }
    let s = score
        .map(|v| format!("{v}/100"))
        .unwrap_or_else(|| "—".into());
    output.print_info(&format!(
        "{}  {}  {s}",
        crate::cli::color::bold(&detail.item.display_name, output.color),
        crate::cli::color::tier_dot(tier, output.color)
    ));
}

fn drift_reprompt(
    output: &OutputConfig,
    inter: Interaction,
    seen: Option<u8>,
    current: Option<u8>,
    findings: &[FindingResponse],
) -> Result<(), SsError> {
    let (Some(seen), Some(current)) = (seen, current) else {
        return Ok(());
    };
    let new_critical = findings
        .iter()
        .any(|f| matches!(f.severity, Severity::High | Severity::Critical));
    if current >= seen && !new_critical {
        return Ok(());
    }
    output.print_warn(&format!(
        "Score changed since you last saw it: {seen} → {current}. Re-review before installing."
    ));
    confirm(output, inter, "Proceed anyway?", false)
}

// ─── severity gate (D-05-19) ─────────────────────────────────────────────────

fn parse_threshold(config: &Config) -> Severity {
    match config.gate_threshold.as_deref() {
        Some("low") => Severity::Low,
        Some("medium") => Severity::Medium,
        Some("high") => Severity::High,
        Some("critical") => Severity::Critical,
        // Default (`info` / unset): the full §5.5 ladder applies.
        _ => Severity::Info,
    }
}

fn apply_severity_gate(
    output: &OutputConfig,
    inter: Interaction,
    config: &Config,
    item: &CatalogItemSummary,
    findings: &[FindingResponse],
) -> Result<(), SsError> {
    if inter.force {
        return Ok(()); // --force bypasses every gate
    }
    let Some(highest) = highest_severity(findings) else {
        return Ok(()); // no findings → silent install
    };
    let threshold = parse_threshold(config);
    if highest.rank() < threshold.rank() {
        return Ok(()); // below the configured silent floor
    }

    match highest {
        Severity::Info => {
            output.print_info("ⓘ This capability has informational findings only.");
            Ok(())
        }
        Severity::Low => {
            output.print_warn("Low-severity findings present — installing.");
            Ok(())
        }
        Severity::Medium => confirm(
            output,
            inter,
            "Medium-severity findings present. Install?",
            false,
        ),
        Severity::High => {
            render_findings(output, findings);
            confirm(
                output,
                inter,
                "High-severity findings present. Install?",
                false,
            )
        }
        Severity::Critical => {
            render_findings(output, findings);
            type_name_gate(output, inter, item)
        }
        Severity::Unknown => Ok(()),
    }
}

/// A Y/N confirm honoring `--yes` (auto-yes up to high) + the non-interactive flag.
fn confirm(
    output: &OutputConfig,
    inter: Interaction,
    prompt: &str,
    default: bool,
) -> Result<(), SsError> {
    if inter.force || inter.yes {
        return Ok(());
    }
    if !can_prompt(inter, output) {
        return Err(
            SsError::new(ERR_NEEDS_FLAG, format!("{prompt} (needs confirmation)"))
                .with_suggestion("Pass --yes to confirm, or --force to override all gates.")
                .with_exit_code(2),
        );
    }
    let ok = inquire::Confirm::new(prompt)
        .with_default(default)
        .prompt()
        .unwrap_or(false);
    if ok {
        Ok(())
    } else {
        Err(SsError::new(ERR_GATE_CANCELLED, "Install cancelled."))
    }
}

/// The critical-tier type-the-name gate. `--yes` does NOT satisfy it — only
/// `--force` (or typing the exact name).
fn type_name_gate(
    output: &OutputConfig,
    inter: Interaction,
    item: &CatalogItemSummary,
) -> Result<(), SsError> {
    output.print_warn("Install is NOT recommended — this capability has critical findings.");
    if inter.force {
        return Ok(());
    }
    if !can_prompt(inter, output) {
        return Err(SsError::new(
            ERR_NEEDS_FLAG,
            "Critical findings require typing the item name to confirm.",
        )
        .with_suggestion("Re-run interactively, or pass --force to override (not recommended).")
        .with_exit_code(2));
    }
    let typed = inquire::Text::new(&format!(
        "Type the item name to confirm (\"{}\"):",
        item.display_name
    ))
    .prompt()
    .unwrap_or_default();
    if typed.trim() == item.display_name {
        Ok(())
    } else {
        Err(SsError::new(
            ERR_GATE_CANCELLED,
            "✗ Install cancelled (name did not match).",
        ))
    }
}

fn render_findings(output: &OutputConfig, findings: &[FindingResponse]) {
    use crate::cli::color;
    output.print_info("");
    for f in findings.iter().take(5) {
        output.print_info(&format_finding_line(f, output.color));
        if let Some(line) = f.evidence_excerpt.as_ref().and_then(|e| e.hit_line()) {
            output.print_info(&color::dim(
                &format!("      {}", line.text.trim_end()),
                output.color,
            ));
        }
        // Inlined remediation action, else the remediation link (D-05-32 reversed).
        let action = f
            .remediation
            .as_ref()
            .map(|r| r.action.as_str())
            .unwrap_or(&f.remediation_link);
        output.print_info(&color::dim(&format!("      → {action}"), output.color));
        // The explanation/severity rationale is verbose-only (keeps the gate tight).
        if output.verbose {
            if let Some(expl) = f.explanation.as_deref() {
                output.print_info(&color::dim(&format!("      {expl}"), output.color));
            }
            if let Some(why) = f.severity_rationale.as_deref() {
                output.print_info(&color::dim(&format!("      {why}"), output.color));
            }
        }
    }
    output.print_info("");
}

/// One finding headline: `<badge>  <rule_id>  <title>` — pure + testable. The
/// title falls back to the rule_id when no prose was inlined on the finding.
pub(crate) fn format_finding_line(f: &FindingResponse, color: bool) -> String {
    use crate::cli::color as c;
    let badge = c::severity_badge(f.severity, color);
    let title = f.title.as_deref().unwrap_or(&f.rule_id);
    format!("  {badge}  {}  {}", f.rule_id, c::dim(title, color))
}

// ─── conflict (D-05-22) ──────────────────────────────────────────────────────

fn resolve_conflict(
    args: &InstallArgs,
    inter: Interaction,
    output: &OutputConfig,
    records: &mut [InstallRecord],
    idx: usize,
) -> Result<(), SsError> {
    if args.update {
        return Ok(()); // re-install / overwrite in place
    }
    if args.reinstall {
        let prior = records[idx].changes.clone();
        crate::agents::writer::revert_changes(&prior)?;
        output.print_substep("Reverted the previous install for a clean reinstall.");
        return Ok(());
    }
    if !can_prompt(inter, output) {
        return Err(SsError::new(
            ERR_CONFLICT,
            format!("\"{}\" is already installed.", records[idx].name),
        )
        .with_suggestion("Pass --update to update it in place, or --reinstall to replace it.")
        .with_exit_code(5));
    }
    let choice = inquire::Select::new(
        &format!("\"{}\" is already installed. What now?", records[idx].name),
        vec!["Update in place", "Reinstall (replace)", "Cancel"],
    )
    .prompt()
    .unwrap_or("Cancel");
    match choice {
        "Update in place" => Ok(()),
        "Reinstall (replace)" => {
            let prior = records[idx].changes.clone();
            crate::agents::writer::revert_changes(&prior)?;
            Ok(())
        }
        _ => Err(SsError::new(ERR_GATE_CANCELLED, "Install cancelled.").with_exit_code(5)),
    }
}

// ─── resolved-item build + install + rollback ────────────────────────────────

/// Whether a registry record matches a user-typed name (slug / display / the
/// capability tail). Shared by uninstall / update / list.
pub(crate) fn record_matches(r: &InstallRecord, name: &str) -> bool {
    r.slug.eq_ignore_ascii_case(name)
        || r.name.eq_ignore_ascii_case(name)
        || capability_name(&r.slug, &r.kind).eq_ignore_ascii_case(name)
}

/// The server/skill identifier — the `<name>` tail of the slug minus the kind
/// prefix (`acme--repo--mcp-server-github` + `mcp_server` → `github`).
pub(crate) fn capability_name(slug: &str, kind: &str) -> String {
    let tail = slug.rsplit("--").next().unwrap_or(slug);
    let prefix = format!("{}-", kind.replace('_', "-"));
    tail.strip_prefix(&prefix).unwrap_or(tail).to_string()
}

/// Best-effort MCP launch entry from the catalog coordinates (D-05-16). The
/// command is a documented heuristic (`npx -y <org/repo>`); the per-agent
/// key-name landmine (not the command) is the load-bearing contract.
fn derive_mcp_entry(item: &CatalogItemSummary) -> Value {
    let pkg = match (&item.github_org, &item.github_repo) {
        (Some(o), Some(r)) => format!("{o}/{r}"),
        _ => capability_name(&item.slug, &item.kind),
    };
    json!({ "command": "npx", "args": ["-y", pkg], "env": {} })
}

pub(crate) async fn build_resolved_item(
    api: &Api,
    item: &CatalogItemSummary,
    kind: &str,
    output: &OutputConfig,
) -> Result<ResolvedItem, SsError> {
    let name = capability_name(&item.slug, kind);
    match kind {
        "mcp_server" => Ok(ResolvedItem {
            slug: item.slug.clone(),
            name,
            kind: kind.to_string(),
            mcp_entry: Some(derive_mcp_entry(item)),
            skill_zip: None,
        }),
        "skill" => {
            let spinner = output.create_spinner("Downloading skill files…");
            let zip = api.download_item_zip(&item.slug).await;
            if let Some(pb) = spinner {
                pb.finish_and_clear();
            }
            Ok(ResolvedItem {
                slug: item.slug.clone(),
                name,
                kind: kind.to_string(),
                mcp_entry: None,
                skill_zip: Some(zip?),
            })
        }
        other => Err(SsError::new(
            ERR_WRITER_UNSUPPORTED,
            format!("This CLI installs Skills + MCP servers; `{other}` is not supported."),
        )),
    }
}

fn install_to_agents(
    output: &OutputConfig,
    chosen: &[DetectedAgent],
    resolved: &ResolvedItem,
) -> Result<Vec<InstallChange>, SsError> {
    let mut applied: Vec<InstallChange> = Vec::new();
    for agent in chosen {
        let writer = writers::writer_for(agent.id);
        match writer.install(resolved, agent, false) {
            Ok(changes) => {
                for c in &changes {
                    output.print_step(&format!("{} — {}", agent.id.display_name(), describe(c)));
                }
                applied.extend(changes);
            }
            Err(e) => {
                output.print_warn(&format!(
                    "Install failed for {} — rolling back.",
                    agent.id.display_name()
                ));
                if let Err(rb) = crate::agents::writer::revert_changes(&applied) {
                    return Err(SsError::new(
                        ERR_WRITE_ROLLBACK,
                        format!(
                            "Install failed ({}) and rollback also failed ({}).",
                            e.message, rb.message
                        ),
                    )
                    .with_suggestion("Run `saferskills doctor` to inspect the on-disk state."));
                }
                return Err(SsError::new(
                    ERR_WRITE_ROLLBACK,
                    format!(
                        "Install failed: {}. Partial changes were reverted.",
                        e.message
                    ),
                )
                .with_suggestion("Run `saferskills doctor` to confirm a clean state."));
            }
        }
    }
    if resolved.kind == "mcp_server" {
        output.print_substep(
            "Verify the MCP launch command in your config — SaferSkills used a best-effort default.",
        );
    }
    Ok(applied)
}

fn describe(change: &InstallChange) -> String {
    match change {
        InstallChange::File { path } => format!("copied {path}"),
        InstallChange::ConfigKey { file, .. } => format!("updated {file}"),
    }
}

fn print_plan(
    output: &OutputConfig,
    chosen: &[DetectedAgent],
    resolved: &ResolvedItem,
) -> Result<(), SsError> {
    let mut plan: Vec<Value> = Vec::new();
    for agent in chosen {
        let writer = writers::writer_for(agent.id);
        let changes = writer.install(resolved, agent, true)?;
        for c in &changes {
            output.print_substep(&format!(
                "[dry-run] {} — {}",
                agent.id.display_name(),
                describe(c)
            ));
        }
        plan.push(json!({ "agent": agent.id.as_str(), "changes": changes.len() }));
    }
    if output.is_json() {
        output.print_json(&json!({ "dry_run": true, "plan": plan }));
    }
    Ok(())
}

async fn maybe_report(api: &Api, slug: &str, chosen: &[DetectedAgent], kind: &str) {
    // Install reporting is unconditional — no consent — suppressed only by a
    // universal kill-switch (CI / DO_NOT_TRACK / SAFERSKILLS_NO_TELEMETRY) or a
    // source build with no baked key.
    if !telemetry::install_reporting_allowed() {
        return;
    }
    let version = env!("CARGO_PKG_VERSION");
    for agent in chosen {
        // Fail-open: a failed report must never fail the install.
        let _ = api
            .report_install(slug, agent.id.as_str(), kind, version)
            .await;
    }
}

fn success_screen(output: &OutputConfig, summary: &CatalogItemSummary) {
    if output.is_json() {
        return;
    }
    output.print_info("");
    output.print_step("Installed.");
    output.print_info("  • saferskills list   — see what's installed");
    output.print_info(&format!(
        "  • saferskills info {}   — full report",
        capability_name(&summary.slug, &summary.kind)
    ));
}

/// Re-run an install over an existing record's agents (update / doctor --fix).
/// Reuses the full gated flow with `--update` semantics so the score is
/// re-verified and the gate re-applied.
pub(crate) async fn reinstall_existing(
    record: &InstallRecord,
    inter: Interaction,
    output: &OutputConfig,
) -> Result<(), SsError> {
    let args = InstallArgs {
        name: record.slug.clone(),
        to: record.agents.clone(),
        all: false,
        project: false,
        update: true,
        reinstall: false,
        seen_score: record.seen_score,
        dry_run: false,
    };
    run_install(&args, inter, output).await
}

/// Re-verify a registry record's writers (used by `doctor`).
pub(crate) fn verify_record(record: &InstallRecord) -> Vec<(AgentId, VerifyStatus)> {
    let mut out = Vec::new();
    let resolved = ResolvedItem {
        slug: record.slug.clone(),
        name: capability_name(&record.slug, &record.kind),
        kind: record.kind.clone(),
        mcp_entry: None,
        skill_zip: None,
    };
    for agent_id in &record.agents {
        let Some(id) = AgentId::from_canonical(agent_id) else {
            continue;
        };
        for scope in [Scope::Global, Scope::Project] {
            if let Some(agent) = crate::agents::detect::detect(id, scope) {
                let status = writers::writer_for(id).verify(&resolved, &agent);
                out.push((id, status));
                break;
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn capability_name_strips_kind_prefix() {
        assert_eq!(
            capability_name("acme--repo--mcp-server-github", "mcp_server"),
            "github"
        );
        assert_eq!(
            capability_name("acme--kit--skill-pdf-extract", "skill"),
            "pdf-extract"
        );
        assert_eq!(capability_name("plain", "skill"), "plain");
    }

    #[test]
    fn derive_mcp_entry_uses_github_coords() {
        let item = sample(
            "acme--repo--mcp-server-github",
            "mcp_server",
            Some("acme"),
            Some("repo"),
        );
        let entry = derive_mcp_entry(&item);
        assert_eq!(entry["command"], "npx");
        assert_eq!(entry["args"][1], "acme/repo");
    }

    fn finding(
        rule_id: &str,
        title: Option<&str>,
        remediation_action: Option<&str>,
    ) -> FindingResponse {
        FindingResponse {
            id: "f1".into(),
            rule_id: rule_id.into(),
            severity: Severity::High,
            sub_score: "security".into(),
            penalty: 12,
            status_at_scan: "active".into(),
            file_path: "server.py".into(),
            line_start: 1,
            line_end: None,
            matched_content_sha256: "0".repeat(64),
            remediation_link: "https://example.com/fix".into(),
            rubric_version: "abc1234".into(),
            evidence_excerpt: None,
            title: title.map(String::from),
            explanation: None,
            category_label: None,
            severity_rationale: None,
            remediation: remediation_action.map(|a| crate::api::dto::FindingRemediation {
                action: a.into(),
                steps: None,
                safer_pattern: None,
            }),
        }
    }

    #[test]
    fn finding_line_uses_inline_title() {
        let f = finding(
            "SS-MCP-RULE-01",
            Some("Poisoned tool description"),
            Some("Remove the tag"),
        );
        let line = format_finding_line(&f, false);
        assert!(line.contains("SS-MCP-RULE-01"));
        assert!(line.contains("Poisoned tool description"));
    }

    #[test]
    fn finding_line_falls_back_to_rule_id() {
        // No inlined prose → the rule_id stands in for the title.
        let f = finding("SS-MCP-RULE-02", None, None);
        let line = format_finding_line(&f, false);
        assert!(line.contains("SS-MCP-RULE-02"));
    }

    #[test]
    fn threshold_parsing_defaults_to_info() {
        let mut c = Config::default();
        assert_eq!(parse_threshold(&c), Severity::Info);
        c.gate_threshold = Some("high".into());
        assert_eq!(parse_threshold(&c), Severity::High);
    }

    fn sample(slug: &str, kind: &str, org: Option<&str>, repo: Option<&str>) -> CatalogItemSummary {
        CatalogItemSummary {
            id: "id".into(),
            slug: slug.into(),
            kind: kind.into(),
            display_name: "X".into(),
            description: None,
            github_url: None,
            github_org: org.map(String::from),
            github_repo: repo.map(String::from),
            source_kind: None,
            popularity_tier: "emerging".into(),
            popularity_score: 0,
            latest_scan_score: None,
            latest_scan_tier: None,
            latest_scan_at: None,
            findings_count: 0,
            registries: vec![],
            agent_compatibility: vec![],
            updated_at: None,
        }
    }
}
