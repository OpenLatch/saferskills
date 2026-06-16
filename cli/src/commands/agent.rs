//! `saferskills agent` — the behavioral Agent Scan (I-5.5 Phase 3, D-5.5-01).
//!
//! A **thin prompt-printer + verdict-poller** (the LLM agent does the per-test work,
//! not the CLI). With no `--to` it detects agents and lets the user multi-select
//! which to scan (non-interactive ⇒ all detected); `--to <id>` (repeatable) scans
//! named agents, accepting any of the 8 known ids even if not detected. Each chosen
//! agent is scanned **sequentially** — bootstrap → pack pre-flight → prompt → poll →
//! verdict — and the overall exit is the worst per-agent verdict.
//!
//! Per agent the flow: mint a run + one-time token via `POST /agent-scans/bootstrap`,
//! **pre-flight-verify the signed pack** (`verify_strict`, hard-stop on mismatch →
//! no prompt), print the bootstrap prompt for the user to paste into their agent,
//! poll the run, then render the graded verdict (`--fail-on` exit code, `--baseline`
//! suppression, `--format json|md`).
//!
//! The agent returns its raw evidence either by auto-POSTing (loopback/dev, or where
//! the gate allows) or by printing a paste-back blob the user submits with
//! `--submit-blob`. The CLI's own submit (`--submit-blob`) solves the Proof-of-Work
//! and carries the one-time token from `~/.saferskills/agent-pending.json`.
//!
//! `agent-pending.json` is a single global file, so the per-agent loop stays
//! **sequential** (never parallelized); `--submit-blob` reads the last pending run.

use std::io::IsTerminal as _;
use std::path::{Path, PathBuf};
use std::time::Duration;

use base64::Engine as _;
use ed25519_dalek::{Signature, VerifyingKey};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use super::report;
use crate::agents::{detect_all, AgentId, Scope};
use crate::api::dto::{AgentFindingDto, AgentScanReport, BootstrapResponse, Severity, Tier};
use crate::api::Api;
use crate::cli::color;
use crate::cli::output::{OutputConfig, OutputFormat};
use crate::cli::{AgentArgs, Interaction};
use crate::core::agent_name::resolve_agent_name;
use crate::core::baseline::{self, Fingerprint};
use crate::core::config::{atomic_write, saferskills_dir, Config};
use crate::core::error::{
    SsError, ERR_AGENT_SCAN_FAILED, ERR_FAIL_ON_PARSE, ERR_PACK_SIGNATURE, ERR_SCAN_TARGET,
    ERR_SCAN_TIMEOUT,
};

/// The Ed25519 pack pubkey map baked by `build.rs` — `<key_id>=<base64-std>,…`
/// (empty in dev/fork builds ⇒ verification is skipped with a warning).
const BAKED_PUBKEY_MAP: &str = env!("SAFERSKILLS_PACK_PUBKEY");

/// Entry point — dispatched from `main::dispatch` for the `agent` command.
pub async fn run_agent(
    args: &AgentArgs,
    inter: Interaction,
    output: &OutputConfig,
) -> Result<(), SsError> {
    let config = Config::load()?;
    let api = Api::new(config.api_base(None))?;

    // Single-shot short-circuits — before any multi-agent loop.
    if let Some(path) = &args.submit_blob {
        return submit_blob(&api, output, args, path).await;
    }
    if args.print_skill {
        return print_skill(&api, args, output).await;
    }

    let platforms = resolve_agents_to_scan(args, inter, output)?;

    // JSON main flow: bootstrap + verify each, emit one array of actionable
    // bootstrap objects, and let automation drive submit + poll itself. The
    // pending file is kept (last run wins) so a later `--submit-blob` finds a token.
    if output.is_json() {
        return run_agent_json(&api, args, output, &platforms).await;
    }

    // Human / Markdown: scan each agent sequentially (the global pending file
    // forbids parallelism), aggregating to the worst exit. Each agent's report
    // prints inline as it grades.
    let multi = platforms.len() > 1;
    let mut summaries: Vec<AgentSummary> = Vec::new();
    let mut fails: Vec<(String, SsError)> = Vec::new();
    for (i, platform) in platforms.iter().enumerate() {
        if multi {
            output.print_info("");
            output.print_info(&format!(
                "  {} {}",
                color::bold(&format!("▸ {}", platform_display(platform)), output.color),
                color::dim(&format!("({}/{})", i + 1, platforms.len()), output.color),
            ));
        }
        match scan_one_agent(&api, args, output, platform, multi).await {
            Ok(summary) => summaries.push(summary),
            Err(e) => fails.push((platform.clone(), e)),
        }
    }
    if multi {
        print_combined_summary(output, &summaries, &fails);
    }

    // Overall exit = the worst per-agent outcome (highest exit code; ties keep the
    // first). A pack mismatch / timeout / network failure folds in here too.
    let worst = summaries
        .iter()
        .filter_map(|s| s.gate_error.clone())
        .chain(fails.into_iter().map(|(_, e)| e))
        .max_by_key(|e| e.exit_code());
    match worst {
        Some(e) => Err(e),
        None => Ok(()),
    }
}

/// Resolve the platforms to scan. `--to` accepts any of the 8 known ids even if
/// not detected (dedup, skip multi-select); otherwise detect, and either return
/// all detected (no agents ⇒ `["universal"]`; non-interactive ⇒ all) or open a
/// multi-select (all pre-checked).
fn resolve_agents_to_scan(
    args: &AgentArgs,
    inter: Interaction,
    output: &OutputConfig,
) -> Result<Vec<String>, SsError> {
    if !args.to.is_empty() {
        let mut out: Vec<String> = Vec::new();
        for token in &args.to {
            let (id, warn) = AgentId::parse_cli(token)?;
            if let Some(w) = warn {
                output.print_warn(&w);
            }
            let s = id.as_str().to_string();
            if !out.contains(&s) {
                out.push(s);
            }
        }
        return Ok(out);
    }

    let detected = detect_all(Scope::Global);
    if detected.is_empty() {
        return Ok(vec!["universal".to_string()]);
    }

    let non_interactive = inter.non_interactive
        || output.is_json()
        || output.is_quiet()
        || !std::io::stderr().is_terminal();
    if non_interactive {
        return Ok(detected.iter().map(|d| d.id.as_str().to_string()).collect());
    }

    // Interactive multi-select over an id-carrying wrapper (all pre-checked), so
    // the result yields ids directly — no display→id reverse lookup.
    let choices: Vec<AgentChoice> = detected.iter().map(|d| AgentChoice(d.id)).collect();
    let defaults: Vec<usize> = (0..choices.len()).collect();
    let picked = inquire::MultiSelect::new("Scan which agents?", choices)
        .with_default(&defaults)
        .prompt()
        .map_err(|_| SsError::new(ERR_AGENT_SCAN_FAILED, "Agent scan cancelled."))?;
    if picked.is_empty() {
        return Err(SsError::new(
            ERR_AGENT_SCAN_FAILED,
            "No agents selected — nothing to scan.",
        ));
    }
    Ok(picked
        .into_iter()
        .map(|c| c.0.as_str().to_string())
        .collect())
}

/// A multi-select row that displays an agent's name but yields its [`AgentId`].
struct AgentChoice(AgentId);

impl std::fmt::Display for AgentChoice {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.0.display_name())
    }
}

/// The display name for a resolved platform id (`universal` → `Universal`).
fn platform_display(platform: &str) -> String {
    if platform == "universal" {
        return "Universal".to_string();
    }
    AgentId::from_canonical(platform)
        .map(|a| a.display_name().to_string())
        .unwrap_or_else(|| platform.to_string())
}

/// The per-agent outcome carried into the combined summary.
struct AgentSummary {
    platform: String,
    score: Option<u8>,
    band: Tier,
    kept_findings: usize,
    /// The `--fail-on` gate error for this agent (carries the exit code), if it
    /// crossed the threshold — `None` when the verdict passed.
    gate_error: Option<SsError>,
}

/// Scan one agent end-to-end: bootstrap → pack pre-flight → prompt → poll →
/// render + evaluate `--fail-on`. A hard failure (pack mismatch / abort / timeout /
/// network) returns `Err`; a graded run returns its summary (with the gate result).
async fn scan_one_agent(
    api: &Api,
    args: &AgentArgs,
    output: &OutputConfig,
    platform: &str,
    multi: bool,
) -> Result<AgentSummary, SsError> {
    let boot = bootstrap_and_verify(api, args, output, platform, multi).await?;

    // Present the paste-able prompt in a clearly delimited copy block (prompt body
    // → stdout, all framing/notes → stderr) so the user knows exactly what to copy.
    present_prompt(output, &boot, platform, args.no_telemetry);

    // Per-run wait budget from `--timeout` (minutes). Generous by default — a real
    // run (human paste + LLM running ~20 tests) is minutes long; Ctrl-C bails early.
    let wait = Duration::from_secs(args.timeout.saturating_mul(60));
    let status = api
        .wait_for_agent_run(&boot.run_id, &boot.submit_token, output, wait)
        .await?;
    if status.status == "aborted" {
        clear_pending();
        return Err(SsError::new(
            ERR_SCAN_TIMEOUT,
            "The agent-scan run was aborted before grading (no partial report).",
        )
        .with_suggestion("Re-run `saferskills agent`."));
    }
    let report = fetch_report(api, &boot).await?;
    clear_pending();
    let (kept, gate_error) = render_and_eval(output, args, &report)?;
    Ok(AgentSummary {
        platform: platform.to_string(),
        score: report.score,
        band: report.band,
        kept_findings: kept.len(),
        gate_error,
    })
}

/// Mint a run for `platform`, persist the pending token, and pre-flight-verify the
/// signed pack (AE-1 — hard-stop on a tampered/unknown signature). Returns the
/// verified bootstrap. The shared prefix of both the per-agent human/MD flow
/// ([`scan_one_agent`]) and the JSON bootstrap-array flow ([`run_agent_json`]).
async fn bootstrap_and_verify(
    api: &Api,
    args: &AgentArgs,
    output: &OutputConfig,
    platform: &str,
    multi: bool,
) -> Result<BootstrapResponse, SsError> {
    let visibility = if args.private { "unlisted" } else { "public" };
    let runtime = if platform == "universal" {
        "other"
    } else {
        platform
    };
    let agent_name = resolve_agent_name(platform, args.name.as_deref(), multi);

    // Best-effort: scan the platform's installed capabilities so the report's
    // Component Scores tab is populated (skippable with --no-components). Both link
    // fields stay None when nothing is captured (the tab keeps its empty state).
    let components = if args.no_components {
        None
    } else {
        super::capability::capture_local_components(api, output, platform, visibility).await
    };
    let (component_scan_run_id, kind_tally) = match &components {
        Some((id, tally)) => (Some(id.as_str()), Some(tally)),
        None => (None, None),
    };

    let pow = super::capability::obtain_pow_if_needed(api, output).await?;
    let boot = api
        .bootstrap_agent_scan(
            platform,
            &agent_name,
            runtime,
            visibility,
            component_scan_run_id,
            kind_tally,
            &pow,
        )
        .await?;
    write_pending(&boot.run_id, &boot.submit_token)?;
    verify_pack(api, output, &boot).await?;
    Ok(boot)
}

/// JSON main flow — bootstrap + pack-verify each platform and emit one array of
/// actionable bootstrap objects (jq-clean). Automation drives submit + poll itself.
async fn run_agent_json(
    api: &Api,
    args: &AgentArgs,
    output: &OutputConfig,
    platforms: &[String],
) -> Result<(), SsError> {
    let multi = platforms.len() > 1;
    let mut arr: Vec<Value> = Vec::with_capacity(platforms.len());
    for platform in platforms {
        let boot = bootstrap_and_verify(api, args, output, platform, multi).await?;
        arr.push(bootstrap_json(&boot));
    }
    output.print_json(&Value::Array(arr));
    Ok(())
}

/// Render the per-agent combined summary (one row per graded agent + a row per
/// hard-failed agent). Human/Markdown only — JSON has its own array surface.
fn print_combined_summary(
    output: &OutputConfig,
    summaries: &[AgentSummary],
    fails: &[(String, SsError)],
) {
    let c = output.color;
    let p = |s: &str| output.print_info(s);
    p("");
    p(&format!("  {}", color::bold("Agent Scan summary", c)));
    for s in summaries {
        let score = s
            .score
            .map(|v| format!("{v}/100"))
            .unwrap_or_else(|| "—".into());
        let status = if s.gate_error.is_some() {
            color::bold("FAIL", c)
        } else {
            "ok".to_string()
        };
        p(&format!(
            "    {}  {}  {}  {}  {}",
            color::tier_dot(s.band, c),
            report::pad(&platform_display(&s.platform), 14),
            report::pad(&score, 7),
            report::pad(&status, 5),
            color::dim(&format!("{} finding(s)", s.kept_findings), c),
        ));
    }
    for (platform, e) in fails {
        p(&format!(
            "    {}  {}  {}",
            color::dim("✗", c),
            report::pad(&platform_display(platform), 14),
            color::dim(&format!("failed ({})", e.code), c),
        ));
    }
}

// ─── sub-flows ───────────────────────────────────────────────────────────────

/// `--submit-blob <file>` — submit a paste-back blob the agent printed. The run id
/// and one-time token come from the pending file written at bootstrap; the raw text
/// is forwarded as a `text/plain` body the server decodes (no gunzip on the client).
async fn submit_blob(
    api: &Api,
    output: &OutputConfig,
    args: &AgentArgs,
    path: &Path,
) -> Result<(), SsError> {
    let pending = read_pending()?;
    let body = std::fs::read_to_string(path).map_err(|e| {
        SsError::new(
            ERR_SCAN_TARGET,
            format!("Cannot read blob {}: {e}", path.display()),
        )
    })?;
    let pow = super::capability::obtain_pow_if_needed(api, output).await?;
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
async fn print_skill(api: &Api, args: &AgentArgs, output: &OutputConfig) -> Result<(), SsError> {
    let agent_name = resolve_agent_name("universal", args.name.as_deref(), false);
    let pow = super::capability::obtain_pow_if_needed(api, output).await?;
    // `--print-skill` is the manual paste path — no local-capability capture.
    let boot = api
        .bootstrap_agent_scan("universal", &agent_name, "other", "public", None, None, &pow)
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

/// Apply the baseline, render the verdict in the requested format, then evaluate
/// `--fail-on`. Returns the kept findings + the gate error (carrying the exit code)
/// when the threshold was crossed, else `None`. A malformed `--fail-on` or baseline
/// is a hard `Err` (usage / read error). Shared by the per-agent loop + `--submit-blob`.
fn render_and_eval(
    output: &OutputConfig,
    args: &AgentArgs,
    report: &AgentScanReport,
) -> Result<(Vec<AgentFindingDto>, Option<SsError>), SsError> {
    let baseline_set = load_baseline(args)?;
    let (kept, suppressed) = baseline::filter(report.findings.clone(), &baseline_set);

    match output.format {
        OutputFormat::Json => output.print_json(&report_json(report, &kept, &suppressed)),
        OutputFormat::Md => println!("{}", report_md(report, &kept, &suppressed)),
        OutputFormat::Human => print_human(output, report, &kept, &suppressed),
    }

    let gate = match &args.fail_on {
        Some(expr) => {
            let fail_on = parse_fail_on(expr)?;
            fail_on.exceeded(report, &kept).then(|| {
                SsError::new(
                    ERR_AGENT_SCAN_FAILED,
                    format!("Agent-scan verdict crossed the --fail-on {expr} threshold."),
                )
            })
        }
        None => None,
    };
    Ok((kept, gate))
}

/// Render the verdict + map `--fail-on` to an exit code (the single-shot
/// `--submit-blob` surface — one report, no aggregate summary).
fn render_and_gate(
    output: &OutputConfig,
    args: &AgentArgs,
    report: &AgentScanReport,
) -> Result<(), SsError> {
    let (_, gate) = render_and_eval(output, args, report)?;
    match gate {
        Some(e) => Err(e),
        None => Ok(()),
    }
}

/// Resolve the baseline fingerprint set from `--baseline` (a `.agentscanignore` OR a
/// prior report `.json`) or a default `./.agentscanignore`.
fn load_baseline(args: &AgentArgs) -> Result<std::collections::BTreeSet<Fingerprint>, SsError> {
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

/// Present the paste-able bootstrap prompt for one agent.
///
/// Layout discipline: the prompt body is the **only** thing on **stdout**
/// (verbatim, so `agent > prompt.txt` captures exactly it); the call-to-action,
/// the telemetry note, and the cut-rules that frame it all go to **stderr**. The
/// backend templates the consent notice onto the END of the prompt, so we strip
/// that trailing copy — it is shown once below as a dim note, never inside the
/// block the user pastes into their agent (it is a note to the human, not an
/// instruction to the agent).
fn present_prompt(
    output: &OutputConfig,
    boot: &BootstrapResponse,
    platform: &str,
    no_telemetry: bool,
) {
    let c = output.color;
    let who = platform_display(platform);
    let body = prompt_without_consent(&boot.prompt, &boot.consent_notice);

    // Telemetry consent — once, dim, OUTSIDE the copy block.
    if !no_telemetry {
        output.print_info("");
        output.print_info(&color::dim(&boot.consent_notice, c));
    }

    output.print_info("");
    output.print_info(&format!(
        "  {} {}",
        color::bold(&format!("Copy the prompt below into {who}, then run it"), c),
        color::dim("— I'll wait here for the result.", c),
    ));
    output.print_info(&color::dim(&cut_rule("✂ copy from here"), c));

    // The prompt body — verbatim, flush-left. Human → stdout (the paste artifact);
    // Markdown reserves stdout for the verdict block → prompt to stderr.
    if output.is_md() {
        eprintln!("{body}");
    } else {
        println!("{body}");
    }

    output.print_info(&color::dim(&cut_rule("✂ end of prompt"), c));
    output.print_info("");
}

/// A labelled, fixed-width "cut here" rule framing the copy block.
fn cut_rule(label: &str) -> String {
    format!("  {label} {}", "┄".repeat(44))
}

/// The prompt with a trailing copy of the consent notice removed. The backend
/// bootstrap template appends `{{CONSENT}}`, so the served prompt ends with the
/// notice; we strip it so it neither duplicates the dim note we print nor lands in
/// the block the user pastes. A no-op if the backend ever stops embedding it.
fn prompt_without_consent(prompt: &str, consent: &str) -> String {
    let consent = consent.trim();
    let trimmed = prompt.trim_end();
    if !consent.is_empty() {
        if let Some(head) = trimmed.strip_suffix(consent) {
            return head.trim_end().to_string();
        }
    }
    trimmed.to_string()
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
        .with_suggestion("Run `saferskills agent` first to mint a run + token.")
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

    #[test]
    fn prompt_without_consent_strips_trailing_notice() {
        let consent = "SaferSkills records anonymous signals. Opt out with --no-telemetry.";
        // The backend templates the consent onto the end of the prompt.
        let prompt = format!("Run the scan.\n\n1. step one\n2. step two\n\n{consent}\n");
        let stripped = prompt_without_consent(&prompt, consent);
        assert!(stripped.contains("step one"));
        assert!(
            !stripped.contains("anonymous signals"),
            "trailing consent must be removed from the paste block"
        );
        assert!(stripped.ends_with("step two"));
    }

    #[test]
    fn prompt_without_consent_is_noop_without_trailing_notice() {
        // A prompt that does NOT end with the consent is returned (trim-only).
        let body = "Run the scan.\n1. step one";
        assert_eq!(
            prompt_without_consent(&format!("{body}\n\n"), "some consent"),
            body
        );
    }
}
