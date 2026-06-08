//! `saferskills scan [target]` / `scan --local`.
//!
//! With a target it scans a single artifact; with no target (or `--local`) it
//! audits everything installed across detected agents.
//!
//! Sends local content (or a GitHub URL) to the API, which scans it server-side
//! and returns a public-by-default run report (`--private` → unlisted + a share
//! token + 90-day expiry). The headless human-gate is a stateless Proof-of-Work
//! challenge (D-05-30) since the CLI can't solve a Turnstile CAPTCHA.

use std::collections::HashSet;
use std::fs;
use std::io::{Cursor, Write as _};
use std::path::{Path, PathBuf};
use std::time::Duration;

use serde_json::json;

use crate::api::dto::ScanRunReportDetail;
use crate::api::Api;
use crate::cli::color;
use crate::cli::output::OutputConfig;
use crate::cli::ScanArgs;
use crate::core::config::Config;
use crate::core::error::{SsError, ERR_POW_FAILED, ERR_RATE_LIMITED, ERR_SCAN_TARGET};
use crate::core::{pow, registry};

/// Client-side wait for a single interactive scan to finish.
const SCAN_TIMEOUT: Duration = Duration::from_secs(180);
/// Show the PoW spinner only when the difficulty is high enough to be felt.
const SPINNER_DIFFICULTY: u32 = 16;

/// Entry point. A GitHub URL or a local path is scanned directly; with neither a
/// target nor `--local`, defaults to a local audit of everything installed.
pub async fn run_scan(args: &ScanArgs, output: &OutputConfig) -> Result<(), SsError> {
    let config = Config::load()?;
    let api = Api::new(config.api_base(None))?;
    let visibility = if args.private { "unlisted" } else { "public" };

    // An explicit target (and no `--local`) scans that single artifact.
    if !args.local {
        if let Some(t) = args.target.as_deref() {
            return if is_github_url(t) {
                scan_url(&api, output, t, visibility).await
            } else {
                scan_path(&api, output, Path::new(t), visibility).await
            };
        }
        // No target given → audit everything installed, like `scan --local`.
        output.print_info(
            "No target given — auditing installed capabilities (same as `scan --local`).",
        );
    }
    run_local(&api, output, visibility).await
}

// ─── single-target paths ─────────────────────────────────────────────────────

async fn scan_url(
    api: &Api,
    output: &OutputConfig,
    url: &str,
    visibility: &str,
) -> Result<(), SsError> {
    let pow = obtain_pow(api, output).await?;
    let submitted = api.submit_scan_url(url, visibility, &pow).await?;
    let run = api
        .wait_for_run(&submitted.id, output, SCAN_TIMEOUT)
        .await?;
    print_run_report(output, api.base(), &run, submitted.share_url.as_deref());
    Ok(())
}

async fn scan_path(
    api: &Api,
    output: &OutputConfig,
    path: &Path,
    visibility: &str,
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
    let pow = obtain_pow(api, output).await?;
    let up = api
        .submit_scan_upload(zip_bytes, &filename, visibility, None, &pow)
        .await?;
    let run = api.wait_for_run(&up.id, output, SCAN_TIMEOUT).await?;
    print_run_report(output, api.base(), &run, up.share_url.as_deref());
    Ok(())
}

// ─── scan --local: enumerate installed (D-05-27) ─────────────────────────────

async fn run_local(api: &Api, output: &OutputConfig, visibility: &str) -> Result<(), SsError> {
    let records = registry::load()?;
    if records.is_empty() {
        output.print_info("No installed capabilities found — nothing to audit.");
        if output.is_json() {
            output.print_json(&json!({ "data": [], "rate_limited": false }));
        }
        return Ok(());
    }

    // Resolve each installed slug to its repo URL, deduping by URL (idempotency
    // dedups to the canonical catalog item anyway; this keeps us well under the
    // PoW-path `cli_scan_submit` daily budget). Slugs with no GitHub provenance
    // (uploads) are warned + skipped for v1.
    let mut seen_urls: HashSet<String> = HashSet::new();
    let mut targets: Vec<(String, String)> = Vec::new(); // (github_url, display_name)
    for rec in &records {
        match api.get_item(&rec.slug).await {
            Ok(detail) => match detail.item.github_url {
                Some(url) if !url.is_empty() => {
                    if seen_urls.insert(url.clone()) {
                        targets.push((url, rec.name.clone()));
                    }
                }
                _ => output.print_warn(&format!(
                    "{} has no GitHub provenance — re-scan with `saferskills scan <path>`.",
                    rec.name
                )),
            },
            Err(_) => output.print_warn(&format!(
                "Could not resolve {} in the catalog — skipping.",
                rec.name
            )),
        }
    }

    let total = targets.len();
    let mut results: Vec<serde_json::Value> = Vec::new();
    let mut rate_limited = false;
    for (url, name) in targets {
        // A fresh single-use challenge per submit.
        let pow = match obtain_pow(api, output).await {
            Ok(p) => p,
            Err(e) if e.code == ERR_RATE_LIMITED => {
                rate_limited = true;
                break;
            }
            Err(e) => {
                output.print_warn(&format!("Skipping {name}: {}", e.message));
                continue;
            }
        };
        match api.submit_scan_url(&url, visibility, &pow).await {
            Ok(resp) => {
                let report_url = resp
                    .share_url
                    .clone()
                    .unwrap_or_else(|| format!("{}/scans/{}", api.base(), resp.id));
                output.print_step(&format!("Submitted {name}"));
                results.push(json!({
                    "name": name,
                    "github_url": url,
                    "run_id": resp.id,
                    "report_url": report_url,
                }));
            }
            Err(e) if e.code == ERR_RATE_LIMITED => {
                rate_limited = true;
                break;
            }
            Err(e) => output.print_warn(&format!("Skipping {name}: {}", e.message)),
        }
    }

    if rate_limited {
        output.print_warn(&format!(
            "Daily scan limit reached: {} of {total} submitted. Retry tomorrow.",
            results.len()
        ));
    } else {
        output.print_step(&format!(
            "{} of {total} submitted for scanning.",
            results.len()
        ));
    }
    if output.is_json() {
        output.print_json(&json!({ "data": results, "rate_limited": rate_limited }));
    }
    Ok(())
}

// ─── Proof-of-Work ───────────────────────────────────────────────────────────

/// Fetch a challenge, solve it off the reactor, and build the header value.
async fn obtain_pow(api: &Api, output: &OutputConfig) -> Result<String, SsError> {
    let challenge = api.get_cli_challenge().await.map_err(|e| {
        // Surface a PoW-specific hint, but preserve a rate-limit code so the
        // caller (scan --local) can stop gracefully.
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

/// Pack `root` (a file or directory) into a byte-stable `.zip`: entries sorted,
/// `/`-separators, a fixed mtime + `0o644` perms, fixed compression. `.git` is
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
    files.sort_by(|a, b| a.0.cmp(&b.0));
    let count = files.len();

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
    Ok((buf, count))
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

// ─── target classification + report ──────────────────────────────────────────

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

fn print_run_report(
    output: &OutputConfig,
    base: &str,
    run: &ScanRunReportDetail,
    share_url: Option<&str>,
) {
    let report_url = share_url
        .map(String::from)
        .unwrap_or_else(|| format!("{base}/scans/{}", run.id));

    if output.is_json() {
        output.print_json(&json!({
            "run_id": run.id,
            "score": run.repo_aggregate_score,
            "tier": run.repo_tier,
            "report_url": report_url,
            "visibility": run.visibility,
            "expires_at": run.expires_at,
        }));
        return;
    }

    output.print_info("");
    output.print_info(&format!(
        "{}  {}/100",
        color::tier_dot(run.repo_tier, output.color),
        run.repo_aggregate_score
    ));
    for cap in &run.capabilities {
        output.print_substep(&format!(
            "{}  {}  {}/100",
            cap.name,
            color::tier_dot(cap.tier, output.color),
            cap.aggregate_score
        ));
    }
    output.print_step(&format!("Report: {report_url}"));
    if share_url.is_some() {
        output.print_info("Unlisted — reachable only via this link; expires in 90 days.");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

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
}
