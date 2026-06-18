//! `saferskills capability [TARGET]`.
//!
//! With a TARGET it scans a single artifact; with no target it audits everything
//! installed across detected agents (optionally scoped by `--to <agent>`).
//!
//! **The no-target audit** enumerates every capability *already installed*
//! across the user's detected agents — reading each agent's own config dirs/files
//! ([`crate::agents::enumerate`]), not the CLI's install ledger — bundles them
//! into one structured `.zip` (paths matching the backend `discovery.py` anchor
//! layout, so the server runs the same directory-based discovery a GitHub repo
//! gets), uploads it **once**, and renders a single per-capability audit report.
//! Because `capability <url>` / `capability <path>` / the no-target audit all
//! resolve to the same [`ScanRunReportDetail`], the rich [`print_run_report`]
//! renderer upgrades every scan surface.
//!
//! Local content (or a GitHub URL) is sent to the API, which scans it server-side
//! and returns a public-by-default run report (`--private` → unlisted + a share
//! token + 90-day expiry). The headless human-gate is a stateless Proof-of-Work
//! challenge since the CLI can't solve a Turnstile CAPTCHA.

use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::io::{Cursor, Write as _};
use std::path::{Path, PathBuf};
use std::time::Duration;

use serde_json::{json, Value};

use super::report;
use crate::agents::enumerate::{self, Enumeration, SkipNote};
use crate::agents::{detect_all, AgentId, DetectedAgent, Scope};
use crate::api::dto::{CapabilityRow, FindingResponse, ScanRunReportDetail, Severity};
use crate::api::Api;
use crate::cli::color;
use crate::cli::output::OutputConfig;
use crate::cli::CapabilityArgs;
use crate::core::config::{contract_home, Config};
use crate::core::error::{SsError, ERR_POW_FAILED, ERR_RATE_LIMITED, ERR_SCAN_TARGET};
use crate::core::pow;
use crate::core::scan_cache::{self, CachedScan};

/// Client-side wait for a single interactive scan to finish.
const SCAN_TIMEOUT: Duration = Duration::from_secs(180);
/// Show the PoW spinner only when the difficulty is high enough to be felt.
const SPINNER_DIFFICULTY: u32 = 16;
/// The backend's hard multipart-body cap (10 MiB compressed) — the bundle must
/// stay under it.
const UPLOAD_MAX_BYTES: usize = 10 * 1024 * 1024;

/// Entry point. A GitHub URL or a local path is scanned directly; with no target,
/// defaults to a local audit of everything installed (optionally scoped by `--to`).
pub async fn run_capability(args: &CapabilityArgs, output: &OutputConfig) -> Result<(), SsError> {
    let config = Config::load()?;
    let api = Api::new(config.api_base(None))?;
    let visibility = if args.private { "unlisted" } else { "public" };

    // An explicit target scans that single artifact (clap rejects `--to` here).
    if let Some(t) = args.target.as_deref() {
        return if is_github_url(t) {
            scan_url(&api, output, t, visibility, args.detailed).await
        } else {
            scan_path(&api, output, Path::new(t), visibility, args.detailed).await
        };
    }
    // No target → audit everything installed (optionally scoped by `--to`).
    if args.to.is_empty() {
        output.print_info("No target given — auditing installed capabilities.");
    }
    run_local_audit(&api, output, visibility, args.detailed, &args.to).await
}

// ─── single-target paths ─────────────────────────────────────────────────────

async fn scan_url(
    api: &Api,
    output: &OutputConfig,
    url: &str,
    visibility: &str,
    detailed: bool,
) -> Result<(), SsError> {
    let pow = obtain_pow_if_needed(api, output).await?;
    let submitted = api.submit_scan_url(url, visibility, &pow).await?;
    let run = api
        .wait_for_run(&submitted.id, output, SCAN_TIMEOUT)
        .await?;
    print_run_report(
        output,
        api.base(),
        &run,
        submitted.share_url.as_deref(),
        detailed,
        None,
    );
    Ok(())
}

async fn scan_path(
    api: &Api,
    output: &OutputConfig,
    path: &Path,
    visibility: &str,
    detailed: bool,
) -> Result<(), SsError> {
    if !path.exists() {
        return Err(SsError::new(
            ERR_SCAN_TARGET,
            format!("No such path: {}", path.display()),
        ));
    }
    let (zip_bytes, count) = deterministic_zip(path)?;
    output.print_substep(&format!("Packed {count} file(s) for upload."));
    let filename = zip_filename(path);
    let pow = obtain_pow_if_needed(api, output).await?;
    let up = api
        .submit_scan_upload(zip_bytes, &filename, visibility, None, &pow)
        .await?;
    let run = api.wait_for_run(&up.id, output, SCAN_TIMEOUT).await?;
    print_run_report(
        output,
        api.base(),
        &run,
        up.share_url.as_deref(),
        detailed,
        None,
    );
    Ok(())
}

// ─── no-target audit: audit everything installed ───────────────────

/// Audit everything installed across detected agents (optionally scoped by
/// `--to`). Shared by `capability` (no target) and `list`'s inline "scan the
/// unscanned now" invitation — the latter calls it (`visibility="public"`, no
/// `--to`) then re-renders from the freshly populated scan cache.
pub(crate) async fn run_local_audit(
    api: &Api,
    output: &OutputConfig,
    visibility: &str,
    detailed: bool,
    to: &[String],
) -> Result<(), SsError> {
    // Resolve the detected agents once, scope them to `--to` (a pure client-side
    // filter), then enumerate from them — keeping the agent list (with its
    // on-disk locations) for the "Agents audited" section.
    let agents = detect_all(Scope::Global);
    let agents = filter_agents_by_to(agents, to, output)?;
    let enm = enumerate::enumerate_from(&agents);
    if enm.capabilities.is_empty() {
        output.print_info("No installed capabilities found across your agents — nothing to audit.");
        output.print_substep(
            "Install one with `saferskills install <name>`, or scan a path: `saferskills capability <path>`.",
        );
        if output.is_json() {
            output.print_json(&json!({
                "run_id": Value::Null,
                "capabilities": [],
                "skipped": skips_json(&enm.skips),
            }));
        }
        return Ok(());
    }

    let BuiltBundle {
        zip: bundle,
        summary,
        skips,
        refs,
    } = build_local_bundle(enm, &agents)?;
    print_preflight(output, &summary, &skips);

    let pow = obtain_pow_if_needed(api, output).await?;
    let up = api
        .submit_scan_upload(bundle, "local-audit.zip", visibility, None, &pow)
        .await?;
    let run = api.wait_for_run(&up.id, output, SCAN_TIMEOUT).await?;

    // Persist each scored capability to the local scan cache so `list` can show
    // its score later (keyed by the CLI-side content hash). Best-effort: a cache
    // write failure must never fail the scan.
    cache_completed_run(output, &run, &refs);

    let local = LocalReport {
        summary: &summary,
        skips: &skips,
    };
    print_run_report(
        output,
        api.base(),
        &run,
        up.share_url.as_deref(),
        detailed,
        Some(&local),
    );
    Ok(())
}

/// Best-effort capture of the scanned platform's installed capabilities for the
/// Agent Report's **Component Scores** tab. Enumerates the platform's agents,
/// bundles their capabilities, and `scan --local`-uploads them (mirroring the agent
/// run's visibility — `--private` ⇒ unlisted), returning the component `scan_run`
/// id + the per-kind tally to link onto the agent run.
///
/// Entirely best-effort: no installed capabilities, an enumeration / bundle error, a
/// PoW failure, or an upload error all yield `None` — the Agent Scan then proceeds
/// behavior-only and the tab keeps its honest empty state.
pub(crate) async fn capture_local_components(
    api: &Api,
    output: &OutputConfig,
    platform: &str,
    visibility: &str,
) -> Option<(String, BTreeMap<String, u32>)> {
    // Scope to the scanned platform's agents (universal = everything on the machine).
    let all = detect_all(Scope::Global);
    let agents: Vec<DetectedAgent> = if platform == "universal" {
        all
    } else {
        let want = AgentId::from_canonical(platform)?;
        all.into_iter().filter(|a| a.id == want).collect()
    };
    if agents.is_empty() {
        return None;
    }
    let enm = enumerate::enumerate_from(&agents);
    if enm.capabilities.is_empty() {
        return None;
    }
    let built = build_local_bundle(enm, &agents).ok()?;

    // Surface clearly BEFORE the upload — a public scan publishes these bytes.
    output.print_step("Scanning your installed capabilities for the report's Component Scores…");
    if visibility == "public" {
        output.print_substep(
            "These are uploaded and published as public catalog items (same as `scan --local`).",
        );
    }
    print_preflight(output, &built.summary, &built.skips);

    let pow = obtain_pow_if_needed(api, output).await.ok()?;
    let up = api
        .submit_scan_upload(built.zip, "agent-components.zip", visibility, None, &pow)
        .await
        .ok()?;
    // Per-kind tally (keys skill/mcp_server/hook/rules/plugin — the backend folds
    // `mcp_server` → `mcp` for the /agents dossier icons).
    let tally: BTreeMap<String, u32> = built
        .summary
        .kinds
        .iter()
        .map(|(k, v)| (k.clone(), *v as u32))
        .collect();
    Some((up.id, tally))
}

/// Scope the detected agents to the `--to` filter (a pure client-side filter — no
/// backend change). Empty `to` keeps every detected agent. Otherwise each token is
/// parsed (canonical id, or a legacy alias that warns; an unknown token is
/// `SS-E-1401` exit 2), a known-but-undetected id **warns and is dropped** (vs the
/// agent-scan path which accepts it), and only the detected agents whose id was
/// requested are kept (detection order preserved). A filter that retains nothing
/// falls through to the existing empty-result branch.
fn filter_agents_by_to(
    agents: Vec<DetectedAgent>,
    to: &[String],
    output: &OutputConfig,
) -> Result<Vec<DetectedAgent>, SsError> {
    if to.is_empty() {
        return Ok(agents);
    }
    let mut requested: Vec<AgentId> = Vec::new();
    for token in to {
        let (id, warn) = AgentId::parse_cli(token)?;
        if let Some(w) = warn {
            output.print_warn(&w);
        }
        if !requested.contains(&id) {
            requested.push(id);
        }
    }
    let detected: std::collections::HashSet<AgentId> = agents.iter().map(|a| a.id).collect();
    for id in &requested {
        if !detected.contains(id) {
            output.print_warn(&format!(
                "`{}` is not detected on this machine — skipping it.",
                id.as_str()
            ));
        }
    }
    Ok(agents
        .into_iter()
        .filter(|a| requested.contains(&a.id))
        .collect())
}

/// CLI-side identity of one bundled capability, used to correlate a server
/// [`CapabilityRow`] back to its local bytes (→ the scan cache `content_hash`).
struct LocalCapRef {
    /// The capability subtree path (the anchor's parent dir) — the server's
    /// `component_path` for a directory capability, the primary correlation key.
    component_dir: String,
    kind: String,
    name: String,
    content_hash: String,
}

/// Correlate one server [`CapabilityRow`] back to a bundled local capability:
/// match on `component_path` (exact, or either-direction subtree prefix) first,
/// then fall back to `(kind, name)`. Returns the local `content_hash`.
fn correlate<'a>(row: &CapabilityRow, refs: &'a [LocalCapRef]) -> Option<&'a LocalCapRef> {
    if let Some(cp) = row.component_path.as_deref().filter(|s| !s.is_empty()) {
        if let Some(r) = refs.iter().find(|r| {
            r.component_dir == cp
                || is_subtree(&r.component_dir, cp)
                || is_subtree(cp, &r.component_dir)
        }) {
            return Some(r);
        }
    }
    refs.iter()
        .find(|r| r.kind == row.kind && r.name == row.name)
}

/// Whether `path` lies under `prefix` as a `/`-segment subtree (`a/b/c` under
/// `a/b`) — allocation-free (no `format!` in the correlation hot loop).
fn is_subtree(path: &str, prefix: &str) -> bool {
    path.len() > prefix.len() && path.starts_with(prefix) && path.as_bytes()[prefix.len()] == b'/'
}

/// Write each scored capability of a completed run to the local scan cache.
/// Best-effort — logs a substep on failure, never errors.
fn cache_completed_run(output: &OutputConfig, run: &ScanRunReportDetail, refs: &[LocalCapRef]) {
    let now = chrono::Utc::now();
    let report_url = run.report_url.clone();
    let cached: Vec<CachedScan> = run
        .capabilities
        .iter()
        .filter_map(|row| {
            correlate(row, refs).map(|r| CachedScan {
                content_hash: r.content_hash.clone(),
                kind: row.kind.clone(),
                name: row.name.clone(),
                catalog_slug: row.catalog_slug.clone(),
                score: row.aggregate_score,
                tier: row.tier,
                scanned_at: now,
                report_url: report_url.clone(),
            })
        })
        .collect();
    if cached.is_empty() {
        return;
    }
    if let Err(e) = scan_cache::upsert(cached) {
        output.print_substep(&format!(
            "Could not update the local scan cache: {}",
            e.message
        ));
    }
}

/// One audited agent — display name + on-disk location + how many of its
/// capabilities the bundle kept.
struct AgentReport {
    name: String,
    location: String,
    capabilities: usize,
}

/// Counts describing the bundled local-audit upload (pre-flight + JSON).
struct BundleSummary {
    capabilities: usize,
    /// Agents that contributed at least one capability (the verdict's "N agents").
    agents: usize,
    /// How many of `capabilities` came from decomposing the Claude plugin cache —
    /// surfaced as a pre-flight hint so the (now much larger) count is explained.
    from_plugins: usize,
    files: usize,
    bytes: usize,
    kinds: BTreeMap<String, usize>,
    /// Per-agent detail (name + location + capability count) for EVERY detected
    /// agent, in detection order — empty ones (count 0) are shown too.
    agents_detail: Vec<AgentReport>,
}

/// The local-audit extras merged into the run report (title override + bundle
/// summary + skips).
struct LocalReport<'a> {
    summary: &'a BundleSummary,
    skips: &'a [SkipNote],
}

/// The assembled local-audit upload plus everything the caller needs after it:
/// the pre-flight `summary`, the excluded-item `skips`, and the per-capability
/// `refs` that correlate a server `CapabilityRow` back to its local bytes (→ the
/// scan cache).
struct BuiltBundle {
    zip: Vec<u8>,
    summary: BundleSummary,
    skips: Vec<SkipNote>,
    refs: Vec<LocalCapRef>,
}

/// Assemble the single structured `.zip`: priority + total-budget selection,
/// casefold-dedup, then a byte-stable zip. Guards the 10 MiB compressed cap.
fn build_local_bundle(enm: Enumeration, agents: &[DetectedAgent]) -> Result<BuiltBundle, SsError> {
    let Enumeration {
        capabilities,
        mut skips,
    } = enm;
    let (kept, budget_skips) = enumerate::select_within_budget(capabilities);
    skips.extend(budget_skips);

    let mut agent_counts: HashMap<AgentId, usize> = HashMap::new();
    let mut kinds: BTreeMap<String, usize> = BTreeMap::new();
    let mut entries: Vec<(String, Vec<u8>)> = Vec::new();
    let mut refs: Vec<LocalCapRef> = Vec::new();
    let mut from_plugins = 0usize;
    for cap in &kept {
        *agent_counts.entry(cap.agent).or_default() += 1;
        *kinds.entry(cap.kind.as_str().to_string()).or_default() += 1;
        // Caps decomposed from the plugin cache mount under `<agent>/plugins/…`.
        if cap.anchor.contains("/plugins/") {
            from_plugins += 1;
        }
        // The capability subtree the server sees as `component_path` is the
        // anchor's parent dir; compute the content hash on the same enumerated
        // entries `list` will re-derive, so the join is exact.
        refs.push(LocalCapRef {
            component_dir: anchor_dir(&cap.anchor),
            kind: cap.kind.as_str().to_string(),
            name: cap.name.clone(),
            content_hash: cap.content_hash(),
        });
        for (p, b) in &cap.entries {
            entries.push((p.clone(), b.clone()));
        }
    }
    // Per-agent detail for EVERY detected agent, in detection order — agents with
    // no installed capability are shown (`no capabilities found`) so the section
    // matches `doctor`'s detection list and the gap is self-explanatory. The
    // verdict / pre-flight "N agents" count, by contrast, is the agents that
    // actually contributed a capability.
    let agents_detail: Vec<AgentReport> = agents
        .iter()
        .map(|a| AgentReport {
            name: a.id.display_name().to_string(),
            location: agent_location(a),
            capabilities: agent_counts.get(&a.id).copied().unwrap_or(0),
        })
        .collect();
    let agents_with_capabilities = agents_detail.iter().filter(|a| a.capabilities > 0).count();
    entries.sort_by(|a, b| a.0.cmp(&b.0));
    let (entries, _dropped) = enumerate::casefold_dedup(entries);

    let files = entries.len();
    let bytes: usize = entries.iter().map(|(_, b)| b.len()).sum();
    let zip = zip_from_entries(entries)?;
    if zip.len() > UPLOAD_MAX_BYTES {
        return Err(SsError::new(
            ERR_SCAN_TARGET,
            format!(
                "Local audit bundle is {} compressed — over the 10 MiB upload cap.",
                human_bytes(zip.len())
            ),
        )
        .with_suggestion(
            "Too many large capabilities to audit at once; scan a single path with `saferskills capability <path>`.",
        ));
    }

    let summary = BundleSummary {
        capabilities: kept.len(),
        agents: agents_with_capabilities,
        from_plugins,
        files,
        bytes,
        kinds,
        agents_detail,
    };
    Ok(BuiltBundle {
        zip,
        summary,
        skips,
        refs,
    })
}

/// The capability subtree path — an anchor's parent dir (`a/b/SKILL.md` →
/// `a/b`), the server's `component_path` for a directory capability. A
/// segment-less anchor yields `""` (whole-bundle root).
fn anchor_dir(anchor: &str) -> String {
    match anchor.rsplit_once('/') {
        Some((dir, _)) => dir.to_string(),
        None => String::new(),
    }
}

/// A `~`-contracted display location for a detected agent — its config root
/// (`~/.claude`, `~/.cursor`, …), derived from the skills dir or MCP config path.
fn agent_location(a: &DetectedAgent) -> String {
    let root = a
        .skill_dir
        .as_ref()
        .and_then(|d| d.parent())
        .or_else(|| a.mcp_config_path.parent())
        .unwrap_or(a.mcp_config_path.as_path());
    contract_home(root)
}

/// The discovery summary printed before the upload submits.
fn print_preflight(output: &OutputConfig, summary: &BundleSummary, skips: &[SkipNote]) {
    let plugins_hint = if summary.from_plugins > 0 {
        format!(" · {} from plugins", summary.from_plugins)
    } else {
        String::new()
    };
    output.print_step(&format!(
        "Found {} capabilities across {} agents{} · {} · bundle {}",
        summary.capabilities,
        summary.agents,
        plugins_hint,
        kinds_str(&summary.kinds),
        human_bytes(summary.bytes)
    ));
    if !skips.is_empty() {
        let mut counts: BTreeMap<&str, usize> = BTreeMap::new();
        for s in skips {
            *counts.entry(s.reason.label()).or_default() += 1;
        }
        let grouped = counts
            .iter()
            .map(|(r, n)| format!("{n} {r}"))
            .collect::<Vec<_>>()
            .join(", ");
        output.print_warn(&format!(
            "Excluded {} item(s) from the bundle: {grouped}",
            skips.len()
        ));
    }
}

// ─── Proof-of-Work ───────────────────────────────────────────────────────────

/// Solve a PoW unless the API is loopback. The backend exempts loopback callers
/// from the human-verification gate (`security.md` § Public-input handling
/// #5/#12), so a local dev API needs no PoW — and its `/cli-challenge` returns
/// 503 when no `SAFERSKILLS_CLI_POW_SECRET` is configured. Returns `""` to send
/// no PoW header (the submit then rides the server-side loopback exemption).
pub(crate) async fn obtain_pow_if_needed(
    api: &Api,
    output: &OutputConfig,
) -> Result<String, SsError> {
    if base_is_loopback(api.base()) {
        return Ok(String::new());
    }
    obtain_pow(api, output).await
}

/// Whether the resolved API base points at a loopback host (`localhost`,
/// `127.0.0.0/8`, `::1`) — the host the backend's own loopback exemption keys on.
fn base_is_loopback(base: &str) -> bool {
    let after_scheme = base.split("://").nth(1).unwrap_or(base);
    let authority = after_scheme.split('/').next().unwrap_or("");
    let host_port = authority.rsplit('@').next().unwrap_or(authority);
    // Bracketed IPv6 (`[::1]:8000`) vs `host:port`.
    let host = if let Some(rest) = host_port.strip_prefix('[') {
        rest.split(']').next().unwrap_or(rest)
    } else {
        host_port.split(':').next().unwrap_or(host_port)
    };
    host.eq_ignore_ascii_case("localhost") || host == "::1" || host.starts_with("127.")
}

/// Fetch a challenge, solve it off the reactor, and build the header value.
async fn obtain_pow(api: &Api, output: &OutputConfig) -> Result<String, SsError> {
    let challenge = api.get_cli_challenge().await.map_err(|e| {
        // Surface a PoW-specific hint, but preserve a rate-limit code so the
        // caller can stop gracefully.
        if e.code == ERR_RATE_LIMITED {
            e
        } else {
            SsError::new(
                ERR_POW_FAILED,
                format!("Could not obtain a scan challenge: {}", e.message),
            )
            .with_suggestion(
                "If this persists, submit via the web UI at https://saferskills.ai/scan.",
            )
        }
    })?;
    let spinner = if challenge.difficulty >= SPINNER_DIFFICULTY {
        output.create_spinner("Solving proof-of-work…")
    } else {
        None
    };
    let solution = pow::solve_async(challenge.challenge.clone(), challenge.difficulty).await;
    if let Some(pb) = spinner {
        pb.finish_and_clear();
    }
    let solution = solution.ok_or_else(|| {
        SsError::new(
            ERR_POW_FAILED,
            "Could not solve the proof-of-work challenge.",
        )
        .with_suggestion(
            "The server may be misconfigured; try the web UI at https://saferskills.ai/scan.",
        )
    })?;
    Ok(pow::header_value(&challenge.challenge, &solution))
}

// ─── deterministic zip ───────────────────────────────────────────────────────

/// Pack `root` (a file or directory) into a byte-stable `.zip`. `.git` is
/// skipped. Identical inputs → byte-identical archives. Returns `(bytes, count)`.
pub(crate) fn deterministic_zip(root: &Path) -> Result<(Vec<u8>, usize), SsError> {
    let mut files: Vec<(String, Vec<u8>)> = Vec::new();
    if root.is_file() {
        let name = root
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("file")
            .to_string();
        files.push((name, read_file(root)?));
    } else if root.is_dir() {
        collect_dir(root, root, &mut files)?;
    } else {
        return Err(SsError::new(
            ERR_SCAN_TARGET,
            format!("Not a readable file or directory: {}", root.display()),
        ));
    }
    if files.is_empty() {
        return Err(SsError::new(
            ERR_SCAN_TARGET,
            "Nothing to scan — the target is empty.",
        ));
    }
    let count = files.len();
    let buf = zip_from_entries(files)?;
    Ok((buf, count))
}

/// Pack `(rel_path, bytes)` entries into a byte-stable `.zip`: entries sorted,
/// `/`-separators, a fixed mtime + `0o644` perms, fixed compression. Identical
/// inputs → byte-identical archives. The shared zip core for both the
/// single-target pack and the no-target audit bundle.
pub(crate) fn zip_from_entries(mut files: Vec<(String, Vec<u8>)>) -> Result<Vec<u8>, SsError> {
    files.sort_by(|a, b| a.0.cmp(&b.0));
    let mut buf: Vec<u8> = Vec::new();
    {
        let mut zw = zip::ZipWriter::new(Cursor::new(&mut buf));
        let opts = zip::write::SimpleFileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated)
            .unix_permissions(0o644)
            .last_modified_time(zip::DateTime::default());
        for (name, bytes) in &files {
            zw.start_file(name.as_str(), opts).map_err(zip_err)?;
            zw.write_all(bytes).map_err(|e| {
                SsError::new(ERR_SCAN_TARGET, format!("Failed packing {name}: {e}"))
            })?;
        }
        zw.finish().map_err(zip_err)?;
    }
    Ok(buf)
}

fn collect_dir(base: &Path, dir: &Path, out: &mut Vec<(String, Vec<u8>)>) -> Result<(), SsError> {
    let mut entries: Vec<PathBuf> = fs::read_dir(dir)
        .map_err(|e| {
            SsError::new(
                ERR_SCAN_TARGET,
                format!("Cannot read {}: {e}", dir.display()),
            )
        })?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .collect();
    entries.sort();
    for path in entries {
        let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("");
        if name == ".git" {
            continue;
        }
        if path.is_dir() {
            collect_dir(base, &path, out)?;
        } else if path.is_file() {
            let rel = path.strip_prefix(base).unwrap_or(&path);
            let rel_str = rel
                .components()
                .map(|c| c.as_os_str().to_string_lossy().into_owned())
                .collect::<Vec<_>>()
                .join("/");
            out.push((rel_str, read_file(&path)?));
        }
    }
    Ok(())
}

fn read_file(path: &Path) -> Result<Vec<u8>, SsError> {
    fs::read(path).map_err(|e| {
        SsError::new(
            ERR_SCAN_TARGET,
            format!("Cannot read {}: {e}", path.display()),
        )
    })
}

fn zip_err(e: zip::result::ZipError) -> SsError {
    SsError::new(
        ERR_SCAN_TARGET,
        format!("Failed to build the upload archive: {e}"),
    )
}

fn zip_filename(path: &Path) -> String {
    let stem = path
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("artifact");
    if stem.ends_with(".zip") {
        stem.to_string()
    } else {
        format!("{stem}.zip")
    }
}

// ─── target classification ───────────────────────────────────────────────────

/// Hand-rolled GitHub-URL check (no regex dep): `https://github.com/<org>/<repo>`
/// with ≥2 non-empty path segments. Mirrors the backend's accepted shape.
pub(crate) fn is_github_url(s: &str) -> bool {
    let rest = s
        .strip_prefix("https://github.com/")
        .or_else(|| s.strip_prefix("http://github.com/"));
    match rest {
        Some(r) => r.split('/').filter(|p| !p.is_empty()).count() >= 2,
        None => false,
    }
}

// ─── the audit report (shared by url / path / local) ─────────────────────────

/// Render a completed run as an elegant, verdict-first audit report. JSON mode
/// emits one machine object (`run` fields + `capabilities` + `category_means` +
/// `top_findings`, plus `bundle` + `skipped` for a local audit).
fn print_run_report(
    output: &OutputConfig,
    base: &str,
    run: &ScanRunReportDetail,
    share_url: Option<&str>,
    detailed: bool,
    local: Option<&LocalReport>,
) {
    // Prefer the unlisted submit `share_url`, then the server-authoritative
    // public report URL (built from the backend's `public_base_url` — the webapp
    // origin, which differs from the API origin in local dev), then a last-resort
    // fallback for an older server that omits `report_url`.
    let report_url = share_url
        .map(String::from)
        .or_else(|| run.report_url.clone())
        .unwrap_or_else(|| format!("{base}/scans/{}", run.id));

    if output.is_json() {
        output.print_json(&report_json(&report_url, run, local));
        return;
    }
    print_human_report(output, &report_url, run, share_url, detailed, local);
}

fn report_json(report_url: &str, run: &ScanRunReportDetail, local: Option<&LocalReport>) -> Value {
    let capabilities: Vec<Value> = run
        .capabilities
        .iter()
        .map(|c| {
            json!({
                "kind": c.kind,
                "name": c.name,
                "score": c.aggregate_score,
                "tier": c.tier,
                "sub_scores": c.sub_scores,
                "findings_count": c.findings.len(),
                "worst_severity": report::worst_severity(&c.findings).map(report::severity_str),
            })
        })
        .collect();

    let category_means: BTreeMap<String, i64> = category_means(run)
        .into_iter()
        .map(|(k, _, m)| (k.to_string(), m))
        .collect();

    let top_findings: Vec<Value> = top_findings(run)
        .into_iter()
        .map(|(cap, f)| {
            json!({
                "rule_id": f.rule_id,
                "severity": f.severity,
                "title": f.title,
                "file": f.file_path,
                "line": f.line_start,
                "capability": cap,
            })
        })
        .collect();

    let mut obj = json!({
        "run_id": run.id,
        "score": run.repo_aggregate_score,
        "tier": run.repo_tier,
        "report_url": report_url,
        "visibility": run.visibility,
        "expires_at": run.expires_at,
        "capabilities": capabilities,
        "category_means": category_means,
        "top_findings": top_findings,
    });
    if let Some(l) = local {
        obj["bundle"] = bundle_json(l.summary);
        obj["skipped"] = skips_json(l.skips);
    }
    obj
}

fn print_human_report(
    output: &OutputConfig,
    report_url: &str,
    run: &ScanRunReportDetail,
    share_url: Option<&str>,
    detailed: bool,
    local: Option<&LocalReport>,
) {
    let c = output.color;
    let p = |s: &str| output.print_info(s);

    // ── verdict ──
    p("");
    p(&format!("  {}", color::bold(&report_title(run, local), c)));
    p(&format!(
        "  {}   {}      {}",
        color::tier_dot(run.repo_tier, c),
        color::bold(&format!("{}/100", run.repo_aggregate_score), c),
        color::dim(&verdict_meta(run, local), c),
    ));

    // ── category breakdown ──
    let means = category_means(run);
    if !means.is_empty() {
        p("");
        p(&format!(
            "  {}  {}",
            color::bold("Category breakdown", c),
            color::dim("(mean across capabilities)", c)
        ));
        for (_, label, mean) in &means {
            p(&format!(
                "    {}  {}  {}",
                report::pad(label, 13),
                color::bar_gauge(*mean as u8, 10, c),
                mean
            ));
        }
    }

    // ── agents detected (local audit only) ──
    // Every detected agent is listed (matching `doctor`); an agent with no
    // installed capability shows `no capabilities found` rather than vanishing.
    if let Some(l) = local {
        if !l.summary.agents_detail.is_empty() {
            p("");
            p(&format!("  {}", color::bold("Agents detected", c)));
            for a in &l.summary.agents_detail {
                let tail = if a.capabilities == 0 {
                    "no capabilities found".to_string()
                } else if a.capabilities == 1 {
                    "1 capability".to_string()
                } else {
                    format!("{} capabilities", a.capabilities)
                };
                p(&format!(
                    "    {}  {}  {}",
                    report::pad(&a.name, 14),
                    report::pad(&a.location, 24),
                    color::dim(&tail, c)
                ));
            }
        }
    }

    // ── capabilities, worst first ──
    if !run.capabilities.is_empty() {
        p("");
        p(&format!(
            "  {}",
            color::bold("Capabilities  (worst first)", c)
        ));
        let mut caps: Vec<&CapabilityRow> = run.capabilities.iter().collect();
        caps.sort_by(|a, b| {
            a.aggregate_score
                .cmp(&b.aggregate_score)
                .then_with(|| a.name.cmp(&b.name))
        });
        let limit = if detailed {
            caps.len()
        } else {
            caps.len().min(8)
        };
        for cap in caps.iter().take(limit) {
            let marker_plain = format!("{} {}", color::tier_glyph(cap.tier), cap.tier.label());
            let marker = color::tier_paint(cap.tier, &report::pad(&marker_plain, 10), c);
            let score = color::score_paint(
                cap.aggregate_score,
                &report::pad_left(cap.aggregate_score, 3),
                c,
            );
            p(&format!(
                "    {marker} {score}   {}  {}  {}",
                report::pad(report::kind_label(&cap.kind), 5),
                report::pad(&cap.name, 22),
                report::finding_rollup(&cap.findings)
            ));
            if detailed {
                report::print_axes(output, &cap.sub_scores, 8);
            }
        }
        if caps.len() > limit {
            p(&format!(
                "    {}",
                color::dim(
                    &format!("· {} more — see the full report", caps.len() - limit),
                    c
                )
            ));
        }
    }

    // ── most problematic findings ──
    let top = top_findings(run);
    if !top.is_empty() {
        p("");
        p(&format!(
            "  {}",
            color::bold("Most problematic findings", c)
        ));
        for (cap_name, f) in &top {
            report::print_finding_row(output, f, Some(cap_name), detailed, false);
        }

        // ── next ──
        if let Some((cap_name, f)) = top.first() {
            p("");
            p(&format!(
                "  {}    Review {cap_name} ({}) before keeping it installed.",
                color::bold("Next", c),
                report::severity_str(f.severity)
            ));
        }
    }

    // ── report link ──
    p("");
    p(&format!(
        "  {}  → {}",
        color::bold("Report", c),
        color::hyperlink(report_url, report_url, c)
    ));
    if share_url.is_some() {
        p("  Unlisted — reachable only via this link; expires in 90 days.");
    }
}

// ─── report data helpers (pure) ──────────────────────────────────────────────

fn report_title(run: &ScanRunReportDetail, local: Option<&LocalReport>) -> String {
    if local.is_some() {
        return "SaferSkills · local audit".to_string();
    }
    if let Some(url) = &run.github_url {
        if let Some(name) = repo_name_from_url(url) {
            return name;
        }
    }
    "SaferSkills · scan".to_string()
}

fn repo_name_from_url(url: &str) -> Option<String> {
    let rest = url
        .strip_prefix("https://github.com/")
        .or_else(|| url.strip_prefix("http://github.com/"))?;
    let segs: Vec<&str> = rest.split('/').filter(|s| !s.is_empty()).collect();
    if segs.len() >= 2 {
        Some(format!("{}/{}", segs[0], segs[1]))
    } else {
        None
    }
}

fn verdict_meta(run: &ScanRunReportDetail, local: Option<&LocalReport>) -> String {
    let caps = run.capability_count.max(run.capabilities.len() as i64);
    let mut parts = vec![format!("{caps} capabilities")];
    if let Some(l) = local {
        parts.push(format!("{} agents", l.summary.agents));
    }
    parts.join(" · ")
}

/// Mean of each axis over `capabilities[].sub_scores`. Returns only axes present
/// in the data, in fixed display order, as `(key, label, mean)`.
fn category_means(run: &ScanRunReportDetail) -> Vec<(&'static str, &'static str, i64)> {
    let mut out = Vec::new();
    for (key, label) in color::AXES {
        let vals: Vec<i64> = run
            .capabilities
            .iter()
            .filter_map(|c| c.sub_scores.get(key).copied())
            .collect();
        if !vals.is_empty() {
            let sum: i64 = vals.iter().sum();
            let mean = (sum + vals.len() as i64 / 2) / vals.len() as i64; // rounded
            out.push((key, label, mean));
        }
    }
    out
}

/// Every capability's findings flattened, sorted severity-desc then `rule_id`,
/// filtered to medium+ and capped at the top 5. `(capability_name, finding)`.
fn top_findings(run: &ScanRunReportDetail) -> Vec<(String, &FindingResponse)> {
    let mut flat: Vec<(String, &FindingResponse)> = Vec::new();
    for cap in &run.capabilities {
        for f in &cap.findings {
            flat.push((cap.name.clone(), f));
        }
    }
    flat.sort_by(|a, b| {
        b.1.severity
            .rank()
            .cmp(&a.1.severity.rank())
            .then_with(|| a.1.rule_id.cmp(&b.1.rule_id))
    });
    flat.into_iter()
        .filter(|(_, f)| f.severity.rank() >= Severity::Medium.rank())
        .take(5)
        .collect()
}

// ─── JSON sub-objects ────────────────────────────────────────────────────────

fn bundle_json(s: &BundleSummary) -> Value {
    json!({
        "capabilities": s.capabilities,
        "agents": s.agents,
        "from_plugins": s.from_plugins,
        "files": s.files,
        "bytes": s.bytes,
        "kinds": s.kinds,
        "agents_detail": Value::Array(
            s.agents_detail
                .iter()
                .map(|a| json!({
                    "name": a.name,
                    "location": a.location,
                    "capabilities": a.capabilities,
                }))
                .collect(),
        ),
    })
}

fn skips_json(skips: &[SkipNote]) -> Value {
    Value::Array(
        skips
            .iter()
            .map(|s| {
                json!({
                    "path": s.path,
                    "reason": s.reason.as_str(),
                    "agent": s.agent.map(|a| a.as_str()),
                })
            })
            .collect(),
    )
}

// ─── formatting helpers ──────────────────────────────────────────────────────

fn kinds_str(kinds: &BTreeMap<String, usize>) -> String {
    const ORDER: [&str; 5] = ["mcp_server", "skill", "hook", "rules", "plugin"];
    let mut parts = Vec::new();
    for k in ORDER {
        if let Some(n) = kinds.get(k) {
            parts.push(format!("{n} {k}"));
        }
    }
    parts.join(" · ")
}

fn human_bytes(n: usize) -> String {
    if n >= 1024 * 1024 {
        format!("{:.1} MiB", n as f64 / (1024.0 * 1024.0))
    } else if n >= 1024 {
        format!("{} KiB", n / 1024)
    } else {
        format!("{n} B")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::api::dto::Tier;
    use crate::cli::output::OutputFormat;
    use std::collections::BTreeMap;

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

    fn cap(
        name: &str,
        kind: &str,
        score: u8,
        tier: Tier,
        findings: Vec<FindingResponse>,
    ) -> CapabilityRow {
        let mut sub = BTreeMap::new();
        sub.insert("security".to_string(), score as i64);
        sub.insert("supply_chain".to_string(), 80i64);
        CapabilityRow {
            kind: kind.into(),
            name: name.into(),
            component_path: None,
            aggregate_score: score,
            tier,
            scan_id: "s".into(),
            catalog_slug: "slug".into(),
            sub_scores: sub,
            findings,
        }
    }

    fn run() -> ScanRunReportDetail {
        ScanRunReportDetail {
            id: "abc123".into(),
            github_url: None,
            repo_aggregate_score: 68,
            repo_tier: Tier::Yellow,
            kind_tally: BTreeMap::new(),
            capability_count: 3,
            capabilities: vec![
                cap(
                    "pre-commit-runner",
                    "hook",
                    34,
                    Tier::Red,
                    vec![
                        finding(
                            "SS-HOOKS-RCE-CURL-PIPE-01",
                            Severity::Critical,
                            "Pipes a remote script into a shell",
                            "hooks/pre-commit.json",
                            12,
                        ),
                        finding("SS-X-LOW-01", Severity::Low, "minor", "a.py", 1),
                    ],
                ),
                cap(
                    "pdf-extract",
                    "skill",
                    52,
                    Tier::Orange,
                    vec![finding(
                        "SS-SKILL-PATH-ESCAPE-02",
                        Severity::High,
                        "Reads files outside the workspace",
                        "scripts/extract.py",
                        40,
                    )],
                ),
                cap("humanizer", "skill", 91, Tier::Green, vec![]),
            ],
            status: Some("completed".into()),
            visibility: Some("public".into()),
            source_kind: Some("upload".into()),
            share_url: None,
            report_url: None,
            expires_at: None,
        }
    }

    #[test]
    fn base_is_loopback_detects_local_apis() {
        assert!(base_is_loopback("http://localhost:8000"));
        assert!(base_is_loopback("http://127.0.0.1:8001"));
        assert!(base_is_loopback("http://127.5.5.5"));
        assert!(base_is_loopback("http://[::1]:8000"));
        assert!(base_is_loopback("https://LOCALHOST:9000/"));
        assert!(!base_is_loopback("https://saferskills.ai"));
        assert!(!base_is_loopback("https://api.example.com:443/v1"));
        assert!(!base_is_loopback("http://192.168.1.10:8000"));
    }

    #[test]
    fn is_github_url_accepts_org_repo() {
        assert!(is_github_url("https://github.com/acme/widget"));
        assert!(is_github_url("https://github.com/acme/widget/tree/main"));
        assert!(!is_github_url("https://github.com/acme"));
        assert!(!is_github_url("https://example.com/acme/widget"));
        assert!(!is_github_url("/local/path"));
    }

    #[test]
    fn deterministic_zip_is_byte_stable() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(dir.path().join("b.txt"), b"second").unwrap();
        fs::write(dir.path().join("a.txt"), b"first").unwrap();
        fs::create_dir(dir.path().join("sub")).unwrap();
        fs::write(dir.path().join("sub").join("c.md"), b"# c").unwrap();

        let (z1, n1) = deterministic_zip(dir.path()).unwrap();
        let (z2, n2) = deterministic_zip(dir.path()).unwrap();
        assert_eq!(n1, 3);
        assert_eq!(n2, 3);
        assert_eq!(z1, z2, "two packs of the same tree must be byte-identical");
    }

    #[test]
    fn zip_from_entries_is_byte_stable_and_order_independent() {
        let a = vec![
            ("b/y.txt".to_string(), b"y".to_vec()),
            ("a/x.txt".to_string(), b"x".to_vec()),
        ];
        let b = vec![
            ("a/x.txt".to_string(), b"x".to_vec()),
            ("b/y.txt".to_string(), b"y".to_vec()),
        ];
        assert_eq!(zip_from_entries(a).unwrap(), zip_from_entries(b).unwrap());
    }

    #[test]
    fn deterministic_zip_single_file() {
        let dir = tempfile::tempdir().unwrap();
        let f = dir.path().join("SKILL.md");
        fs::write(&f, b"---\nname: t\n---\n").unwrap();
        let (zip, count) = deterministic_zip(&f).unwrap();
        assert_eq!(count, 1);
        assert!(!zip.is_empty());
    }

    #[test]
    fn deterministic_zip_empty_dir_errors() {
        let dir = tempfile::tempdir().unwrap();
        let err = deterministic_zip(dir.path()).unwrap_err();
        assert_eq!(err.code, ERR_SCAN_TARGET);
    }

    #[test]
    fn zip_filename_adds_extension() {
        assert_eq!(zip_filename(Path::new("/x/my-skill")), "my-skill.zip");
        assert_eq!(zip_filename(Path::new("/x/bundle.zip")), "bundle.zip");
    }

    #[test]
    fn category_means_are_mean_over_caps() {
        let r = run();
        let means = category_means(&r);
        // security present on all three (34, 52, 91) → mean 59 (rounded).
        let sec = means.iter().find(|(k, _, _)| *k == "security").unwrap();
        assert_eq!(sec.2, (34 + 52 + 91 + 1) / 3); // rounded
    }

    #[test]
    fn top_findings_severity_desc_medium_plus_only() {
        let r = run();
        let top = top_findings(&r);
        // The Low finding is filtered out; critical sorts first.
        assert_eq!(top.len(), 2);
        assert_eq!(top[0].1.severity, Severity::Critical);
        assert_eq!(top[0].0, "pre-commit-runner");
        assert_eq!(top[1].1.severity, Severity::High);
    }

    #[test]
    fn json_report_keeps_run_fields_and_adds_richness() {
        let r = run();
        let v = report_json("https://saferskills.ai/scans/runs/abc123", &r, None);
        assert_eq!(v["run_id"], "abc123");
        assert_eq!(v["score"], 68);
        assert_eq!(v["tier"], "yellow");
        assert!(v["report_url"].as_str().unwrap().contains("abc123"));
        assert_eq!(v["capabilities"].as_array().unwrap().len(), 3);
        assert!(v["category_means"]["security"].is_number());
        // top_findings: critical first, medium+ only.
        let top = v["top_findings"].as_array().unwrap();
        assert_eq!(top.len(), 2);
        assert_eq!(top[0]["severity"], "critical");
        // No bundle/skipped without a local report.
        assert!(v["bundle"].is_null());
    }

    #[test]
    fn human_report_renders_without_color_or_ansi() {
        // The renderer must not panic and (color off) emit no ANSI / OSC 8.
        let r = run();
        // print_human_report writes to stderr; just assert it doesn't panic and
        // the pure builders behave. Verdict title for a local audit:
        let summary = BundleSummary {
            capabilities: 3,
            agents: 2,
            from_plugins: 1,
            files: 12,
            bytes: 2048,
            kinds: BTreeMap::new(),
            agents_detail: vec![
                AgentReport {
                    name: "Claude Code".into(),
                    location: "~/.claude".into(),
                    capabilities: 11,
                },
                AgentReport {
                    name: "Cursor".into(),
                    location: "~/.cursor".into(),
                    capabilities: 1,
                },
                // A detected-but-empty agent — listed, marked, not counted in
                // `agents` (the verdict's "with capabilities" tally).
                AgentReport {
                    name: "Gemini".into(),
                    location: "~/.gemini".into(),
                    capabilities: 0,
                },
            ],
        };
        let local = LocalReport {
            summary: &summary,
            skips: &[],
        };
        assert_eq!(report_title(&r, Some(&local)), "SaferSkills · local audit");
        // Verdict counts only agents with capabilities (2), even though 3 are
        // detected (the section lists all 3, incl. the empty Gemini).
        assert!(verdict_meta(&r, Some(&local)).contains("2 agents"));
        assert_eq!(local.summary.agents_detail.len(), 3);
        assert_eq!(local.summary.agents_detail[0].name, "Claude Code");
        assert_eq!(local.summary.agents_detail[0].location, "~/.claude");
        assert_eq!(local.summary.agents_detail[2].capabilities, 0);
        print_human_report(
            &out_plain(),
            "https://saferskills.ai/scans/runs/abc123",
            &r,
            None,
            false,
            Some(&local),
        );
    }

    #[test]
    fn report_title_from_github_url() {
        let mut r = run();
        r.github_url = Some("https://github.com/acme/widget".into());
        assert_eq!(report_title(&r, None), "acme/widget");
    }

    #[test]
    fn human_bytes_formats() {
        assert_eq!(human_bytes(512), "512 B");
        assert_eq!(human_bytes(2048), "2 KiB");
        assert_eq!(human_bytes(3 * 1024 * 1024), "3.0 MiB");
    }

    #[test]
    fn anchor_dir_is_parent_of_anchor() {
        assert_eq!(
            anchor_dir("claude-code/skills/pdf/SKILL.md"),
            "claude-code/skills/pdf"
        );
        assert_eq!(anchor_dir("claude-code/hooks/x.json"), "claude-code/hooks");
        assert_eq!(anchor_dir("loose"), "");
    }

    fn cap_ref(dir: &str, kind: &str, name: &str, hash: &str) -> LocalCapRef {
        LocalCapRef {
            component_dir: dir.into(),
            kind: kind.into(),
            name: name.into(),
            content_hash: hash.into(),
        }
    }

    fn row_with(component: Option<&str>, kind: &str, name: &str) -> CapabilityRow {
        CapabilityRow {
            kind: kind.into(),
            name: name.into(),
            component_path: component.map(String::from),
            aggregate_score: 90,
            tier: crate::api::dto::Tier::Green,
            scan_id: "s".into(),
            catalog_slug: "slug".into(),
            sub_scores: BTreeMap::new(),
            findings: vec![],
        }
    }

    #[test]
    fn correlate_matches_on_component_path() {
        let refs = vec![
            cap_ref("claude-code/skills/pdf", "skill", "pdf", "HASH_PDF"),
            cap_ref("claude-code/hooks", "hook", "pre-commit", "HASH_HOOK"),
        ];
        // Exact component_path match.
        let row = row_with(Some("claude-code/skills/pdf"), "skill", "pdf");
        assert_eq!(correlate(&row, &refs).unwrap().content_hash, "HASH_PDF");
        // Subtree match (server path nested under the local component dir).
        let nested = row_with(Some("claude-code/skills/pdf/scripts"), "skill", "pdf");
        assert_eq!(correlate(&nested, &refs).unwrap().content_hash, "HASH_PDF");
    }

    #[test]
    fn is_subtree_requires_segment_boundary() {
        assert!(is_subtree("a/b/c", "a/b"));
        assert!(is_subtree("a/b", "a"));
        assert!(!is_subtree("a/b", "a/b")); // equal is not a subtree
        assert!(!is_subtree("a/bc", "a/b")); // not a segment boundary
        assert!(!is_subtree("a", "a/b")); // shorter than prefix
    }

    #[test]
    fn correlate_falls_back_to_kind_name() {
        let refs = vec![cap_ref(
            "claude-code/skills/pdf",
            "skill",
            "pdf",
            "HASH_PDF",
        )];
        // No component_path on the row → (kind, name) fallback.
        let row = row_with(None, "skill", "pdf");
        assert_eq!(correlate(&row, &refs).unwrap().content_hash, "HASH_PDF");
        // No match at all → None.
        let miss = row_with(None, "skill", "other");
        assert!(correlate(&miss, &refs).is_none());
    }
}
