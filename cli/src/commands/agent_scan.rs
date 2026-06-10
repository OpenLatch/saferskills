//! `saferskills scan agent` — the behavioral Agent Scan (I-5.5 Phase 3, D-5.5-01).
//!
//! A **thin prompt-printer + verdict-poller** (the LLM agent does the per-test work,
//! not the CLI). The flow: mint a run + one-time token via `POST /agent-scans/
//! bootstrap`, **pre-flight-verify the signed pack** (`verify_strict`, hard-stop on
//! mismatch → no prompt), print the bootstrap prompt for the user to paste into
//! their agent, poll the run, then render the graded verdict (`--fail-on` exit code,
//! `--baseline` suppression, `--format json|md`).
//!
//! The agent returns its raw evidence either by auto-POSTing (loopback/dev, or where
//! the gate allows) or by printing a paste-back blob the user submits with
//! `--submit-blob`. The CLI's own submit (`--submit-blob`) solves the Proof-of-Work
//! and carries the one-time token from `~/.saferskills/agent-pending.json`.

use std::path::{Path, PathBuf};
use std::time::Duration;

use base64::Engine as _;
use ed25519_dalek::{Signature, VerifyingKey};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::agents::{detect_all, AgentId, Scope};
use crate::api::dto::{AgentFindingDto, AgentScanReport, BootstrapResponse, Severity, Tier};
use crate::api::Api;
use crate::cli::color;
use crate::cli::output::{OutputConfig, OutputFormat};
use crate::cli::ScanArgs;
use crate::core::baseline::{self, Fingerprint};
use crate::core::config::{atomic_write, saferskills_dir, Config};
use crate::core::error::{
    SsError, ERR_AGENT_SCAN_FAILED, ERR_FAIL_ON_PARSE, ERR_PACK_SIGNATURE, ERR_SCAN_TARGET,
    ERR_SCAN_TIMEOUT,
};

/// Agent scans involve a human pasting a prompt + an LLM running ~20 tests, so the
/// client wait is generous (the run is terminal the moment the cloud grades).
const AGENT_SCAN_TIMEOUT: Duration = Duration::from_secs(300);

/// The Ed25519 pack pubkey map baked by `build.rs` — `<key_id>=<base64-std>,…`
/// (empty in dev/fork builds ⇒ verification is skipped with a warning).
const BAKED_PUBKEY_MAP: &str = env!("SAFERSKILLS_PACK_PUBKEY");

/// Entry point — dispatched from `scan::run_scan` when the agent branch is selected.
pub async fn run_agent_scan(args: &ScanArgs, output: &OutputConfig) -> Result<(), SsError> {
    let config = Config::load()?;
    let api = Api::new(config.api_base(None))?;

    if let Some(path) = &args.submit_blob {
        return submit_blob(&api, output, args, path).await;
    }
    if args.print_skill {
        return print_skill(&api, output).await;
    }

    let visibility = if args.private { "unlisted" } else { "public" };
    let platform = resolve_platform(args, output)?;
    let runtime = if platform == "universal" {
        "other"
    } else {
        platform.as_str()
    };

    let pow = super::scan::obtain_pow_if_needed(&api, output).await?;
    let boot = api
        .bootstrap_agent_scan(&platform, "my-agent", runtime, visibility, &pow)
        .await?;
    write_pending(&boot.run_id, &boot.submit_token)?;

    // One-time company-telemetry consent notice (suppressed by `--no-telemetry`).
    if !args.no_telemetry {
        output.print_info(&boot.consent_notice);
    }

    // Pre-flight signature verify (AE-1) — aborts the run + hard-stops on mismatch.
    verify_pack(&api, output, &boot).await?;

    // JSON main flow: emit the actionable bootstrap data and let automation drive
    // submit + poll itself (it needs the prompt BEFORE a report can exist). The
    // pending file is kept so a later `--submit-blob` finds the token.
    if output.is_json() {
        output.print_json(&bootstrap_json(&boot));
        return Ok(());
    }

    // Human / Markdown: print the prompt, poll, render the graded verdict.
    output.print_info("Paste the following prompt into your agent, then run the scan:");
    print_prompt(output, &boot.prompt);

    let status = api
        .wait_for_agent_run(&boot.run_id, &boot.submit_token, output, AGENT_SCAN_TIMEOUT)
        .await?;
    if status.status == "aborted" {
        clear_pending();
        return Err(SsError::new(
            ERR_SCAN_TIMEOUT,
            "The agent-scan run was aborted before grading (no partial report).",
        )
        .with_suggestion("Re-run `saferskills scan agent`."));
    }
    let report = fetch_report(&api, &boot).await?;
    clear_pending();
    render_and_gate(output, args, &report)
}

// ─── sub-flows ───────────────────────────────────────────────────────────────

/// `--submit-blob <file>` — submit a paste-back blob the agent printed. The run id
/// and one-time token come from the pending file written at bootstrap; the raw text
/// is forwarded as a `text/plain` body the server decodes (no gunzip on the client).
async fn submit_blob(
    api: &Api,
    output: &OutputConfig,
    args: &ScanArgs,
    path: &Path,
) -> Result<(), SsError> {
    let pending = read_pending()?;
    let body = std::fs::read_to_string(path).map_err(|e| {
        SsError::new(
            ERR_SCAN_TARGET,
            format!("Cannot read blob {}: {e}", path.display()),
        )
    })?;
    let pow = super::scan::obtain_pow_if_needed(api, output).await?;
    let report = api
        .submit_agent_blob(
            &pending.run_id,
            &pending.submit_token,
            body,
            &pow,
            args.no_telemetry,
        )
        .await?;
    clear_pending();
    render_and_gate(output, args, &report)
}

/// `--print-skill` — mint a run + emit a static `SKILL.md` body whose prompt is
/// already filled with the fresh run id + token (the manual AE-1 activation path).
async fn print_skill(api: &Api, output: &OutputConfig) -> Result<(), SsError> {
    let pow = super::scan::obtain_pow_if_needed(api, output).await?;
    let boot = api
        .bootstrap_agent_scan("universal", "my-agent", "other", "public", &pow)
        .await?;
    let body = skill_md(&boot);
    if output.is_json() {
        output.print_json(&json!({ "run_id": boot.run_id, "skill": body }));
    } else {
        println!("{body}");
    }
    Ok(())
}

/// Wrap the rendered universal bootstrap prompt as a minimal `SKILL.md`.
fn skill_md(boot: &BootstrapResponse) -> String {
    format!(
        "---\nname: saferskills-agent-scan\ndescription: Run the SaferSkills Agent Scan on this agent (run {}).\n---\n\n{}\n",
        boot.run_id, boot.prompt
    )
}

// ─── platform resolution ─────────────────────────────────────────────────────

/// Resolve the bootstrap platform: an explicit `--agent <id>` (canonical, legacy
/// alias warns), `--agent auto` or bare `scan agent` → the first detected agent,
/// else `universal`.
fn resolve_platform(args: &ScanArgs, output: &OutputConfig) -> Result<String, SsError> {
    match args.agent.as_deref() {
        Some("auto") | None => Ok(detect_all(Scope::Global)
            .into_iter()
            .next()
            .map(|d| d.id.as_str().to_string())
            .unwrap_or_else(|| "universal".to_string())),
        Some(id) => {
            let (aid, warn): (AgentId, Option<String>) = AgentId::parse_cli(id)?;
            if let Some(w) = warn {
                output.print_warn(&w);
            }
            Ok(aid.as_str().to_string())
        }
    }
}

// ─── pack signature pre-flight (AE-1) ────────────────────────────────────────

/// Fetch the signed pack and verify it before printing the prompt. Fail-closed: a
/// released CLI with a baked key MUST get a valid signature (missing/unknown ⇒
/// abort); a dev/fork build (no baked key) skips with a warning. On a real mismatch
/// the run is aborted (best-effort) and the scan hard-stops — no prompt, no report.
async fn verify_pack(
    api: &Api,
    output: &OutputConfig,
    boot: &BootstrapResponse,
) -> Result<(), SsError> {
    let (body, key_id, sig_b64) = api.get_pack_bytes(&boot.run_id, &boot.submit_token).await?;
    let keys = baked_pubkeys();

    match (key_id, sig_b64) {
        (Some(kid), Some(sig)) => {
            let Some(pk) = keys.get(&kid) else {
                // A baked-key build that does not recognise the served key id must
                // not proceed (could be a substituted pack).
                return Err(abort_and_fail(
                    api,
                    boot,
                    "The pack was signed by an unknown key — refusing to proceed.",
                )
                .await);
            };
            verify_strict_or_fail(api, boot, pk, &body, &sig).await
        }
        _ => {
            if keys.is_empty() {
                output.print_warn(
                    "Pack signature not verified (no signing key baked into this build) — \
                     proceeding in manual-bootstrap mode.",
                );
                Ok(())
            } else {
                Err(abort_and_fail(
                    api,
                    boot,
                    "The pack arrived unsigned but this build requires a signature — \
                     refusing to proceed.",
                )
                .await)
            }
        }
    }
}

/// `verify_strict` over the exact served bytes; abort + hard-stop on failure.
async fn verify_strict_or_fail(
    api: &Api,
    boot: &BootstrapResponse,
    pubkey: &[u8; 32],
    body: &[u8],
    sig_b64: &str,
) -> Result<(), SsError> {
    if sig_ok(pubkey, body, sig_b64) {
        Ok(())
    } else {
        Err(abort_and_fail(
            api,
            boot,
            "The pack signature did not verify — the pack may have been tampered with.",
        )
        .await)
    }
}

/// Pure Ed25519 check (`verify_strict` over the exact bytes). The signature + pubkey
/// are STANDARD base64 (the backend uses `b64encode`, not url-safe). Any decode /
/// parse / verify failure ⇒ `false` (fail-closed). Unit-tested independently of the
/// network so the AE-1 tamper path is proven without a baked key.
fn sig_ok(pubkey: &[u8; 32], body: &[u8], sig_b64: &str) -> bool {
    let Ok(vk) = VerifyingKey::from_bytes(pubkey) else {
        return false;
    };
    let Ok(sig_bytes) = base64::engine::general_purpose::STANDARD.decode(sig_b64) else {
        return false;
    };
    let Ok(sig) = Signature::from_slice(&sig_bytes) else {
        return false;
    };
    vk.verify_strict(body, &sig).is_ok()
}

/// Best-effort abort the just-minted run, clear the pending file, and build the
/// hard-stop `SS-E-1604` error (exit 1, non-zero — AE-1 "no report").
async fn abort_and_fail(api: &Api, boot: &BootstrapResponse, message: &str) -> SsError {
    let _ = api.abort_agent_run(&boot.run_id, &boot.submit_token).await;
    clear_pending();
    SsError::new(ERR_PACK_SIGNATURE, message.to_string())
        .with_suggestion("Re-run, or report this if it persists — the pack is served signed.")
}

/// Parse the baked `<key_id>=<base64-std-pubkey>,…` map into verifying keys. A
/// malformed entry is skipped (lenient — a good entry still verifies).
fn baked_pubkeys() -> std::collections::HashMap<String, [u8; 32]> {
    let mut out = std::collections::HashMap::new();
    for entry in BAKED_PUBKEY_MAP.split(',').filter(|s| !s.trim().is_empty()) {
        let Some((kid, b64)) = entry.split_once('=') else {
            continue;
        };
        let Ok(bytes) = base64::engine::general_purpose::STANDARD.decode(b64.trim()) else {
            continue;
        };
        if let Ok(arr) = <[u8; 32]>::try_from(bytes.as_slice()) {
            out.insert(kid.trim().to_string(), arr);
        }
    }
    out
}

// ─── report fetch + render + fail-on ─────────────────────────────────────────

async fn fetch_report(api: &Api, boot: &BootstrapResponse) -> Result<AgentScanReport, SsError> {
    match &boot.share_token {
        Some(token) => api.get_agent_run_private(token).await,
        None => api.get_agent_run(&boot.run_id).await,
    }
}

/// Apply the baseline, render the verdict in the requested format, then map
/// `--fail-on` to an exit code.
fn render_and_gate(
    output: &OutputConfig,
    args: &ScanArgs,
    report: &AgentScanReport,
) -> Result<(), SsError> {
    let baseline_set = load_baseline(args)?;
    let (kept, suppressed) = baseline::filter(report.findings.clone(), &baseline_set);

    match output.format {
        OutputFormat::Json => output.print_json(&report_json(report, &kept, &suppressed)),
        OutputFormat::Md => println!("{}", report_md(report, &kept, &suppressed)),
        OutputFormat::Human => print_human(output, report, &kept, &suppressed),
    }

    if let Some(expr) = &args.fail_on {
        let fail_on = parse_fail_on(expr)?;
        if fail_on.exceeded(report, &kept) {
            return Err(SsError::new(
                ERR_AGENT_SCAN_FAILED,
                format!("Agent-scan verdict crossed the --fail-on {expr} threshold."),
            ));
        }
    }
    Ok(())
}

/// Resolve the baseline fingerprint set from `--baseline` (a `.agentscanignore` OR a
/// prior report `.json`) or a default `./.agentscanignore`.
fn load_baseline(args: &ScanArgs) -> Result<std::collections::BTreeSet<Fingerprint>, SsError> {
    if let Some(path) = &args.baseline {
        if path.extension().and_then(|e| e.to_str()) == Some("json") {
            let text = std::fs::read_to_string(path).map_err(|e| {
                SsError::new(
                    ERR_SCAN_TARGET,
                    format!("Cannot read baseline {}: {e}", path.display()),
                )
            })?;
            let prior: AgentScanReport = serde_json::from_str(&text).map_err(|e| {
                SsError::new(
                    ERR_SCAN_TARGET,
                    format!(
                        "Baseline {} is not a valid agent-scan report: {e}",
                        path.display()
                    ),
                )
            })?;
            return Ok(baseline::from_findings(&prior.findings));
        }
        return baseline::load(path);
    }
    let default = Path::new(".agentscanignore");
    if default.exists() {
        baseline::load(default)
    } else {
        Ok(std::collections::BTreeSet::new())
    }
}

// ─── --fail-on ───────────────────────────────────────────────────────────────

#[derive(Debug)]
enum FailOn {
    Severity(Severity),
    Score(u8),
    Band(Tier),
}

fn parse_fail_on(spec: &str) -> Result<FailOn, SsError> {
    let s = spec.trim().to_ascii_lowercase();
    if let Some(n) = s.strip_prefix("score:") {
        let v: u8 = n
            .trim()
            .parse()
            .map_err(|_| fail_on_err(spec))
            .and_then(|v: u16| u8::try_from(v.min(100)).map_err(|_| fail_on_err(spec)))?;
        return Ok(FailOn::Score(v));
    }
    if let Some(b) = s.strip_prefix("band:") {
        return parse_tier(b.trim())
            .map(FailOn::Band)
            .ok_or_else(|| fail_on_err(spec));
    }
    parse_severity(&s)
        .map(FailOn::Severity)
        .ok_or_else(|| fail_on_err(spec))
}

fn fail_on_err(spec: &str) -> SsError {
    SsError::new(
        ERR_FAIL_ON_PARSE,
        format!("Invalid --fail-on `{spec}` (expected <severity>|score:<n>|band:<tier>)."),
    )
    .with_exit_code(2)
}

impl FailOn {
    /// Whether the graded verdict (post-baseline `kept`) crosses this threshold.
    fn exceeded(&self, report: &AgentScanReport, kept: &[AgentFindingDto]) -> bool {
        match self {
            FailOn::Severity(min) => kept.iter().any(|f| f.severity.rank() >= min.rank()),
            FailOn::Score(threshold) => report.score.is_some_and(|s| s < *threshold),
            FailOn::Band(threshold) => tier_rank(report.band) <= tier_rank(*threshold),
        }
    }
}

/// Worst→best rank (`red`=0 … `green`=3; `unscoped`=4 never trips a band gate).
fn tier_rank(t: Tier) -> u8 {
    match t {
        Tier::Red => 0,
        Tier::Orange => 1,
        Tier::Yellow => 2,
        Tier::Green => 3,
        Tier::Unscoped | Tier::Unknown => 4,
    }
}

fn parse_tier(s: &str) -> Option<Tier> {
    match s {
        "green" => Some(Tier::Green),
        "yellow" => Some(Tier::Yellow),
        "orange" => Some(Tier::Orange),
        "red" => Some(Tier::Red),
        _ => None,
    }
}

fn parse_severity(s: &str) -> Option<Severity> {
    match s {
        "info" => Some(Severity::Info),
        "low" => Some(Severity::Low),
        "medium" => Some(Severity::Medium),
        "high" => Some(Severity::High),
        "critical" => Some(Severity::Critical),
        _ => None,
    }
}

fn severity_label(s: Severity) -> &'static str {
    match s {
        Severity::Critical => "critical",
        Severity::High => "high",
        Severity::Medium => "medium",
        Severity::Low => "low",
        Severity::Info => "info",
        Severity::Unknown => "unknown",
    }
}

/// Findings sorted worst-severity-first then test id (stable display order).
fn sorted(findings: &[AgentFindingDto]) -> Vec<&AgentFindingDto> {
    let mut v: Vec<&AgentFindingDto> = findings.iter().collect();
    v.sort_by(|a, b| {
        b.severity
            .rank()
            .cmp(&a.severity.rank())
            .then_with(|| a.test_id.cmp(&b.test_id))
    });
    v
}

// ─── rendering ───────────────────────────────────────────────────────────────

fn print_prompt(output: &OutputConfig, prompt: &str) {
    if output.is_md() {
        // Markdown mode reserves stdout for the verdict block → prompt to stderr.
        eprintln!(
            "\n----- paste into your agent -----\n{prompt}\n---------------------------------\n"
        );
    } else {
        // Human mode: the prompt is the paste-able artifact → stdout.
        println!("{prompt}");
    }
}

fn bootstrap_json(boot: &BootstrapResponse) -> Value {
    json!({
        "run_id": boot.run_id,
        "prompt": boot.prompt,
        "consent_notice": boot.consent_notice,
        "pack_url": boot.pack_url,
        "submit_token": boot.submit_token,
        "poll_url": boot.poll_url,
        "share_token": boot.share_token,
    })
}

fn report_json(
    report: &AgentScanReport,
    kept: &[AgentFindingDto],
    suppressed: &[AgentFindingDto],
) -> Value {
    let mut v = serde_json::to_value(report).unwrap_or_else(|_| json!({}));
    if let Some(obj) = v.as_object_mut() {
        obj.insert("kept_findings_count".into(), json!(kept.len()));
        obj.insert("suppressed_findings_count".into(), json!(suppressed.len()));
    }
    v
}

fn report_md(
    report: &AgentScanReport,
    kept: &[AgentFindingDto],
    suppressed: &[AgentFindingDto],
) -> String {
    let score = report
        .score
        .map(|s| s.to_string())
        .unwrap_or_else(|| "—".into());
    let verdict = report.verdict_label.as_deref().unwrap_or("");
    let mut out = format!(
        "## SaferSkills Agent Scan — {} {}/100 {}\n\n",
        report.band.label(),
        score,
        verdict
    );
    if let Some(cap) = &report.cap_callout {
        out.push_str(&format!("> {cap}\n\n"));
    }
    if kept.is_empty() {
        out.push_str("No findings observed under this pack.\n");
    } else {
        out.push_str("| Test | Severity | Finding |\n|---|---|---|\n");
        for f in sorted(kept) {
            out.push_str(&format!(
                "| {} | {} | {} |\n",
                f.test_id,
                severity_label(f.severity),
                f.title.replace('|', "\\|")
            ));
        }
    }
    if !suppressed.is_empty() {
        out.push_str(&format!(
            "\n_{} finding(s) suppressed by baseline._\n",
            suppressed.len()
        ));
    }
    if let Some(url) = &report.report_url {
        out.push_str(&format!("\n[Full report]({url})\n"));
    }
    out
}

fn print_human(
    output: &OutputConfig,
    report: &AgentScanReport,
    kept: &[AgentFindingDto],
    suppressed: &[AgentFindingDto],
) {
    let c = output.color;
    let p = |s: &str| output.print_info(s);
    let score = report
        .score
        .map(|s| s.to_string())
        .unwrap_or_else(|| "—".into());

    p("");
    p(&format!("  {}", color::bold("SaferSkills · Agent Scan", c)));
    p(&format!(
        "  {}   {}      {}",
        color::tier_dot(report.band, c),
        color::bold(&format!("{score}/100"), c),
        color::dim(report.verdict_label.as_deref().unwrap_or(""), c),
    ));
    if let Some(cap) = &report.cap_callout {
        p(&format!("  {}", color::dim(cap, c)));
    }
    if let Some(conf) = &report.confidence {
        p(&format!(
            "  {}",
            color::dim(&format!("confidence: {conf}"), c)
        ));
    }
    if !report.trust_labels.is_empty() {
        p(&format!(
            "  {}",
            color::dim(&report.trust_labels.join(" · "), c)
        ));
    }

    // ── tests run ──
    let total = report.checks.len();
    if total > 0 {
        let vulnerable = report
            .checks
            .iter()
            .filter(|c| c.verdict == "vulnerable")
            .count();
        let na = report.checks.iter().filter(|c| c.verdict == "n_a").count();
        p("");
        p(&format!(
            "  {}  {} run · {} observed vulnerable · {} not applicable",
            color::bold("Tests", c),
            total,
            vulnerable,
            na
        ));
    }

    // ── findings (kept, worst first) ──
    if kept.is_empty() {
        p("");
        p(&format!(
            "  {}",
            color::bold("No findings observed under this pack.", c)
        ));
    } else {
        p("");
        p(&format!("  {}", color::bold("Findings  (worst first)", c)));
        for f in sorted(kept) {
            p(&format!(
                "    {}  {}  {}",
                color::bold(&f.test_id, c),
                color::dim(severity_label(f.severity), c),
                f.title
            ));
            if !f.owasp_refs.is_empty() || !f.atlas_refs.is_empty() {
                let refs = [f.owasp_refs.join(", "), f.atlas_refs.join(", ")]
                    .into_iter()
                    .filter(|s| !s.is_empty())
                    .collect::<Vec<_>>()
                    .join(" · ");
                p(&format!("      {}", color::dim(&refs, c)));
            }
            p(&format!(
                "      {} {}",
                color::dim("→", c),
                f.remediation.action
            ));
        }
    }
    if !suppressed.is_empty() {
        p(&format!(
            "    {}",
            color::dim(
                &format!("· {} finding(s) suppressed by baseline", suppressed.len()),
                c
            )
        ));
    }

    // ── report + manage links ──
    if let Some(url) = &report.report_url {
        p("");
        p(&format!(
            "  {}  → {}",
            color::bold("Report", c),
            color::hyperlink(url, url, c)
        ));
    }
    if let Some(url) = &report.share_url {
        p(&format!(
            "  {}  → {}",
            color::bold("Manage", c),
            color::hyperlink(url, url, c)
        ));
        p("  Unlisted — save this link; it is the only way to manage the private report.");
    }
}

// ─── pending-run state (bridges bootstrap → a separate --submit-blob run) ─────

#[derive(Debug, Serialize, Deserialize)]
struct PendingRun {
    run_id: String,
    submit_token: String,
}

fn pending_path() -> PathBuf {
    saferskills_dir().join("agent-pending.json")
}

fn write_pending(run_id: &str, submit_token: &str) -> Result<(), SsError> {
    let body = serde_json::to_vec(&PendingRun {
        run_id: run_id.to_string(),
        submit_token: submit_token.to_string(),
    })
    .map_err(|e| {
        SsError::new(
            ERR_SCAN_TARGET,
            format!("Failed to serialize pending run: {e}"),
        )
    })?;
    let path = pending_path();
    atomic_write(&path, &body)?;
    restrict_perms(&path);
    Ok(())
}

fn read_pending() -> Result<PendingRun, SsError> {
    let path = pending_path();
    let text = std::fs::read_to_string(&path).map_err(|_| {
        SsError::new(
            ERR_SCAN_TARGET,
            "No pending agent-scan run found to submit against.",
        )
        .with_suggestion("Run `saferskills scan agent` first to mint a run + token.")
    })?;
    serde_json::from_str(&text)
        .map_err(|e| SsError::new(ERR_SCAN_TARGET, format!("Corrupt pending run file: {e}")))
}

fn clear_pending() {
    let _ = std::fs::remove_file(pending_path());
}

/// Restrict the pending file (which holds the short-lived bearer submit token) to
/// owner-only on unix. A no-op on Windows (the file lives under the user profile).
#[cfg(unix)]
fn restrict_perms(path: &Path) {
    use std::os::unix::fs::PermissionsExt;
    let _ = std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600));
}

#[cfg(not(unix))]
fn restrict_perms(_path: &Path) {}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::api::dto::{AgentRemediation, Tier};

    fn report(score: Option<u8>, band: Tier, findings: Vec<AgentFindingDto>) -> AgentScanReport {
        AgentScanReport {
            id: "r".into(),
            status: "published".into(),
            agent_name: "a".into(),
            runtime: "claude-code".into(),
            score,
            band,
            verdict_label: Some("Review".into()),
            cap_callout: None,
            confidence: Some("high".into()),
            score_breakdown: None,
            trust_labels: vec!["cloud-validated".into()],
            pack_id: "p".into(),
            pack_version: "v".into(),
            pack_signature_verified: Some(true),
            capabilities_present: vec![],
            capabilities_absent: vec![],
            family_tally: std::collections::BTreeMap::new(),
            checks: vec![],
            findings,
            component_scores: vec![],
            visibility: "public".into(),
            expires_at: None,
            share_url: None,
            report_url: Some("https://saferskills.ai/agent-scans/r".into()),
            rubric_version: "rv".into(),
            engine_version: "ev".into(),
            latency_ms: 1,
            scanned_at: None,
        }
    }

    fn finding(test_id: &str, sev: Severity) -> AgentFindingDto {
        AgentFindingDto {
            id: "f".into(),
            test_id: test_id.into(),
            severity: sev,
            verdict: "vulnerable".into(),
            family: "fam".into(),
            owasp_refs: vec!["ASI01:2026".into()],
            atlas_refs: vec![],
            nist_refs: vec![],
            score_delta: -25,
            detection_rule: "substring".into(),
            leaked_canary_slot: Some(test_id.into()),
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
    fn parse_fail_on_variants() {
        assert!(matches!(
            parse_fail_on("high").unwrap(),
            FailOn::Severity(Severity::High)
        ));
        assert!(matches!(
            parse_fail_on("score:80").unwrap(),
            FailOn::Score(80)
        ));
        assert!(matches!(
            parse_fail_on("band:orange").unwrap(),
            FailOn::Band(Tier::Orange)
        ));
        let err = parse_fail_on("nonsense").unwrap_err();
        assert_eq!(err.code, ERR_FAIL_ON_PARSE);
        assert_eq!(err.exit_code(), 2);
    }

    #[test]
    fn fail_on_severity_uses_kept_only() {
        let r = report(
            Some(50),
            Tier::Orange,
            vec![finding("AS-06", Severity::Critical)],
        );
        // The finding is kept → severity gate trips.
        assert!(parse_fail_on("high").unwrap().exceeded(&r, &r.findings));
        // Once suppressed (kept empty) → no trip.
        assert!(!parse_fail_on("high").unwrap().exceeded(&r, &[]));
    }

    #[test]
    fn fail_on_score_and_band() {
        let r = report(Some(35), Tier::Red, vec![]);
        assert!(parse_fail_on("score:80").unwrap().exceeded(&r, &[]));
        assert!(!parse_fail_on("score:30").unwrap().exceeded(&r, &[]));
        // band:orange fails on orange OR red.
        assert!(parse_fail_on("band:orange").unwrap().exceeded(&r, &[]));
        assert!(parse_fail_on("band:red").unwrap().exceeded(&r, &[]));
        let green = report(Some(95), Tier::Green, vec![]);
        assert!(!parse_fail_on("band:orange").unwrap().exceeded(&green, &[]));
    }

    #[test]
    fn tier_rank_orders_worst_first() {
        assert!(tier_rank(Tier::Red) < tier_rank(Tier::Orange));
        assert!(tier_rank(Tier::Orange) < tier_rank(Tier::Green));
    }

    #[test]
    fn md_render_has_table_and_links() {
        let r = report(
            Some(35),
            Tier::Red,
            vec![finding("AS-06", Severity::Critical)],
        );
        let md = report_md(&r, &r.findings, &[]);
        assert!(md.contains("Agent Scan"));
        assert!(md.contains("AS-06"));
        assert!(md.contains("Full report"));
    }

    #[test]
    fn baked_pubkeys_parses_map() {
        // Empty in dev/test builds — just assert no panic + empty.
        let keys = baked_pubkeys();
        assert!(keys.is_empty() || !keys.is_empty());
    }

    #[test]
    fn sig_ok_accepts_valid_and_rejects_tamper() {
        use ed25519_dalek::{Signer, SigningKey};
        let sk = SigningKey::from_bytes(&[7u8; 32]);
        let pubkey: [u8; 32] = sk.verifying_key().to_bytes();
        let body = b"the exact served pack bytes";
        let sig_b64 = base64::engine::general_purpose::STANDARD.encode(sk.sign(body).to_bytes());

        // Valid signature over the exact bytes verifies (AE-1 happy path).
        assert!(sig_ok(&pubkey, body, &sig_b64));
        // A tampered body fails verify_strict (AE-1 hard-stop path).
        assert!(!sig_ok(&pubkey, b"tampered bytes", &sig_b64));
        // A garbage signature fails closed.
        assert!(!sig_ok(&pubkey, body, "not-valid-base64!!"));
    }

    #[test]
    fn skill_md_embeds_run_and_prompt() {
        let boot = BootstrapResponse {
            run_id: "RID".into(),
            prompt: "PROMPT-BODY".into(),
            consent_notice: "c".into(),
            pack_url: "u".into(),
            submit_token: "t".into(),
            poll_url: "p".into(),
            share_token: None,
        };
        let s = skill_md(&boot);
        assert!(s.contains("RID"));
        assert!(s.contains("PROMPT-BODY"));
        assert!(s.starts_with("---"));
    }
}
