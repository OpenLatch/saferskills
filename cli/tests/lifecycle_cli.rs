//! End-to-end lifecycle coverage through the real binary.
//!
//! Drives `install → list → doctor → update → uninstall` as subprocesses against
//! a mock API, with a **faked** claude-code agent in a throw-away `HOME`. This is
//! the only way to exercise the command-orchestration in `commands/{install,
//! list,update,uninstall,doctor}.rs` — those flows need a detected agent + a live
//! catalog, neither of which a pure unit test has.
//!
//! **Unix-only.** `dirs::home_dir()` honours `$HOME` on unix (Linux + macOS), so
//! a temp-HOME fake agent is detected there; on Windows it reads the OS API and
//! the fake wouldn't be seen. The coverage CI lane runs on Linux, so this is
//! where the command-module coverage comes from. `cargo llvm-cov` merges the
//! subprocess coverage (the same path that already covers `main.rs`).
#![cfg(unix)]

use assert_cmd::Command;
use mockito::{Matcher, Server, ServerGuard};
use predicates::prelude::*;
use tempfile::TempDir;

const SLUG: &str = "acme--gh--github-mcp";

fn item_json(findings: bool) -> serde_json::Value {
    serde_json::json!({
        "id": "id-1",
        "slug": SLUG,
        "kind": "mcp_server",
        "display_name": "github-mcp",
        "github_org": "acme",
        "github_repo": "gh",
        "popularity_tier": "emerging",
        "popularity_score": 10,
        "latest_scan_score": if findings { 61 } else { 92 },
        "latest_scan_tier": if findings { "yellow" } else { "green" },
        "findings_count": if findings { 1 } else { 0 },
        "registries": [],
        "agent_compatibility": ["claude-code"],
        "updated_at": "2026-06-01T00:00:00Z"
    })
}

fn finding_array(findings: bool) -> serde_json::Value {
    if !findings {
        return serde_json::json!([]);
    }
    serde_json::json!([{
        "id": "f1",
        "rule_id": "SS-MCP-POISON-UNICODE-TAG-01",
        "severity": "high",
        "sub_score": "security",
        "penalty": 20,
        "status_at_scan": "active",
        "file_path": "src/server.ts",
        "line_start": 42,
        "matched_content_sha256": "5d41402abc4b2a76b9719d911017c592e3b0c44298fc1c149afbf4c8996fb924",
        "remediation_link": "https://saferskills.ai/r/x",
        "rubric_version": "abc1234",
        "title": "Poisoned tool description",
        "remediation": { "action": "Remove the hidden directive." }
    }])
}

fn detail_json(findings: bool) -> serde_json::Value {
    serde_json::json!({
        "item": item_json(findings),
        "latest_scan": {
            "id": "scan-1",
            "slug": SLUG,
            "display_name": "github-mcp",
            "aggregate_score": if findings { 61 } else { 92 },
            "tier": if findings { "yellow" } else { "green" },
            "sub_scores": {},
            "score_breakdown": {},
            "findings": finding_array(findings),
            "scanned_at": "2026-06-01T00:00:00Z",
            "rubric_version": "abc1234",
            "engine_version": "1.0",
            "latency_ms": 12,
            "source": "github",
            "status": "completed"
        }
    })
}

/// A mock API that resolves `github-mcp`, serves its detail, and answers health.
fn mock_api(findings: bool) -> ServerGuard {
    let mut server = Server::new();
    server
        .mock("GET", "/api/v1/items")
        .match_query(Matcher::Any)
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            serde_json::json!({ "data": [item_json(findings)], "total_count": 1, "page": 1, "total_pages": 1, "page_size": 24 })
                .to_string(),
        )
        .expect_at_least(1)
        .create();
    server
        .mock("GET", format!("/api/v1/items/{SLUG}").as_str())
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(detail_json(findings).to_string())
        .expect_at_least(1)
        .create();
    server
        .mock("GET", "/api/v1/health")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            serde_json::json!({ "status": "ok", "version": "1.0", "git_sha": "abc", "migrations_ok": true })
                .to_string(),
        )
        .create();
    server
}

/// A `saferskills` command isolated from the host: temp `SAFERSKILLS_DIR`, temp
/// `HOME` carrying a faked claude-code surface (`~/.claude.json`), and the mock
/// API. `CI=1` keeps telemetry + the first-run audit/consent prompts off.
fn cli(ss_dir: &std::path::Path, home: &std::path::Path, api: &str) -> Command {
    let mut cmd = Command::cargo_bin("saferskills").unwrap();
    cmd.env("SAFERSKILLS_DIR", ss_dir)
        .env("HOME", home)
        .env("SAFERSKILLS_API_URL", api)
        .env("CI", "1")
        .env("NO_COLOR", "1");
    cmd
}

/// Create a throw-away HOME with a `.claude.json` so claude-code is detected.
fn fake_home() -> TempDir {
    let home = tempfile::tempdir().unwrap();
    std::fs::write(home.path().join(".claude.json"), b"{}\n").unwrap();
    home
}

#[test]
fn full_lifecycle_install_list_doctor_update_uninstall() {
    let ss = tempfile::tempdir().unwrap();
    let home = fake_home();
    let server = mock_api(false);
    let api = server.url();
    let run = || cli(ss.path(), home.path(), &api);

    // 1. install (clean item → no gate) to the faked claude-code agent.
    let out = run()
        .args(["--json", "install", "github-mcp", "--to", "claude-code"])
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let v: serde_json::Value = serde_json::from_slice(&out).expect("install json");
    assert_eq!(v["slug"], SLUG);
    assert_eq!(v["installed"][0], "claude-code");

    // The writer actually merged the MCP entry into the faked ~/.claude.json.
    let claude = std::fs::read_to_string(home.path().join(".claude.json")).unwrap();
    assert!(claude.contains("github-mcp"), "mcp entry written: {claude}");

    // 2. list — one populated row.
    let out = run()
        .args(["--json", "list"])
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let v: serde_json::Value = serde_json::from_slice(&out).unwrap();
    assert_eq!(v["data"][0]["slug"], SLUG);

    // 3. doctor — verifies the installed record against the filesystem.
    run().args(["--json", "doctor"]).assert().success();

    // 4. update --all — same version → "unchanged" (exercises the update_all loop).
    let out = run()
        .args(["--json", "update", "--all"])
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let v: serde_json::Value = serde_json::from_slice(&out).unwrap();
    assert_eq!(v["unchanged"], 1);

    // 5. uninstall — reverts the recorded changes + drops the row.
    run()
        .args(["--json", "uninstall", "github-mcp"])
        .assert()
        .success();

    // 6. list again — empty.
    let out = run()
        .args(["--json", "list"])
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let v: serde_json::Value = serde_json::from_slice(&out).unwrap();
    assert!(v["data"].as_array().unwrap().is_empty());
}

#[test]
fn install_gate_dryrun_and_conflict_paths() {
    let ss = tempfile::tempdir().unwrap();
    let home = fake_home();
    let server = mock_api(true); // item carries a HIGH finding → gate engages
    let api = server.url();
    let run = || cli(ss.path(), home.path(), &api);

    // dry-run: plans, writes nothing, no registry row. `--yes` clears the HIGH
    // gate so the flow reaches the dry-run plan (the gate runs before it).
    run()
        .args([
            "--json",
            "install",
            "github-mcp",
            "--to",
            "claude-code",
            "--yes",
            "--dry-run",
        ])
        .assert()
        .success();
    assert!(
        is_registry_empty(ss.path()),
        "dry-run must not write the registry"
    );

    // real install with a HIGH finding → --yes clears the severity gate.
    run()
        .args([
            "--json",
            "install",
            "github-mcp",
            "--to",
            "claude-code",
            "--yes",
        ])
        .assert()
        .success();

    // second install (no resolution flag) → conflict, exit 5.
    run()
        .args([
            "--json",
            "install",
            "github-mcp",
            "--to",
            "claude-code",
            "--yes",
        ])
        .assert()
        .code(5)
        .stderr(predicate::str::contains("SS-E-1300"));

    // --update resolves the conflict in place.
    run()
        .args([
            "--json",
            "install",
            "github-mcp",
            "--to",
            "claude-code",
            "--yes",
            "--update",
        ])
        .assert()
        .success();
}

fn is_registry_empty(ss_dir: &std::path::Path) -> bool {
    let p = ss_dir.join("installs.json");
    match std::fs::read_to_string(&p) {
        Ok(s) => {
            let v: serde_json::Value = serde_json::from_str(&s).unwrap_or(serde_json::json!([]));
            v.as_array().map(|a| a.is_empty()).unwrap_or(true)
        }
        Err(_) => true,
    }
}
