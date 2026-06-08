//! End-to-end smoke tests for the `saferskills` binary (assert_cmd + mockito).
//!
//! Covers the CLI acceptance surface: `--version` / `--help`, the `info`
//! read path (human + `--json`), did-you-mean on a typo, color stripping,
//! `completion` / `man`, and the `scan` target-error fast path.

use assert_cmd::Command;
use mockito::{Matcher, Server, ServerGuard};
use predicates::prelude::*;

/// A catalog item whose display name + slug-tail both equal `github-mcp`, so an
/// exact `info github-mcp` resolves deterministically.
fn item_json() -> serde_json::Value {
    serde_json::json!({
        "id": "id-1",
        "slug": "acme--gh--github-mcp",
        "kind": "mcp_server",
        "display_name": "github-mcp",
        "popularity_tier": "emerging",
        "popularity_score": 10,
        "latest_scan_score": 87,
        "latest_scan_tier": "green",
        "findings_count": 1,
        "registries": [],
        "agent_compatibility": ["claude-code"],
        "updated_at": "2026-06-01T00:00:00Z"
    })
}

fn detail_json() -> serde_json::Value {
    serde_json::json!({
        "item": item_json(),
        "latest_scan": {
            "id": "scan-1",
            "slug": "acme--gh--github-mcp",
            "display_name": "github-mcp",
            "aggregate_score": 87,
            "tier": "green",
            "sub_scores": {},
            "score_breakdown": {},
            "findings": [{
                "id": "f1",
                "rule_id": "SS-MCP-POISON-UNICODE-TAG-01",
                "severity": "high",
                "sub_score": "security",
                "penalty": 20,
                "status_at_scan": "active",
                "file_path": "src/server.ts",
                "line_start": 42,
                "line_end": 58,
                "matched_content_sha256": "5d41402abc4b2a76b9719d911017c592e3b0c44298fc1c149afbf4c8996fb924",
                "remediation_link": "https://saferskills.ai/r/x",
                "rubric_version": "abc1234",
                "evidence_excerpt": {
                    "file": "src/server.ts",
                    "lines": [{ "line_no": 42, "text": "eval(userInput)", "hit": true }],
                    "truncated": false
                }
            }],
            "scanned_at": "2026-06-01T00:00:00Z",
            "rubric_version": "abc1234",
            "engine_version": "1.0",
            "latency_ms": 12,
            "source": "github",
            "status": "completed"
        }
    })
}

/// Spin up a mock API that resolves `github-mcp` + serves its detail.
fn mock_api() -> ServerGuard {
    let mut server = Server::new();
    server
        .mock("GET", "/api/v1/items")
        .match_query(Matcher::Any)
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(serde_json::json!({ "data": [item_json()], "total_count": 1, "page": 1, "total_pages": 1, "page_size": 24 }).to_string())
        .expect_at_least(1)
        .create();
    server
        .mock("GET", "/api/v1/items/acme--gh--github-mcp")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(detail_json().to_string())
        .create();
    server
}

/// A `saferskills` command isolated from the host (`SAFERSKILLS_DIR` → temp).
fn cli(dir: &std::path::Path) -> Command {
    let mut cmd = Command::cargo_bin("saferskills").unwrap();
    cmd.env("SAFERSKILLS_DIR", dir).env("CI", "1"); // CI=1 keeps telemetry + first-run prompts off
    cmd
}

#[test]
fn version_flag_prints_name_and_version() {
    let tmp = tempfile::tempdir().unwrap();
    cli(tmp.path())
        .arg("--version")
        .assert()
        .success()
        .stdout(predicate::str::contains("saferskills"));
}

#[test]
fn help_lists_full_command_surface() {
    let tmp = tempfile::tempdir().unwrap();
    cli(tmp.path())
        .arg("--help")
        .assert()
        .success()
        .stdout(predicate::str::contains("info"))
        .stdout(predicate::str::contains("install"))
        .stdout(predicate::str::contains("scan"))
        .stdout(predicate::str::contains("completion"));
}

#[test]
fn info_json_emits_clean_stdout() {
    let tmp = tempfile::tempdir().unwrap();
    let server = mock_api();
    let out = cli(tmp.path())
        .env("SAFERSKILLS_API_URL", server.url())
        .args(["--json", "info", "github-mcp"])
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    // stdout must be pure, parseable JSON (jq-clean).
    let v: serde_json::Value = serde_json::from_slice(&out).expect("stdout is valid JSON");
    assert_eq!(v["score"], 87);
    assert_eq!(v["tier"], "green");
    assert_eq!(v["slug"], "acme--gh--github-mcp");
    assert!(v["report_url"]
        .as_str()
        .unwrap()
        .ends_with("/items/acme--gh--github-mcp"));
    assert_eq!(v["findings"][0]["rule_id"], "SS-MCP-POISON-UNICODE-TAG-01");
}

#[test]
fn info_human_renders_score_and_findings_to_stderr() {
    let tmp = tempfile::tempdir().unwrap();
    let server = mock_api();
    cli(tmp.path())
        .env("SAFERSKILLS_API_URL", server.url())
        .env("NO_COLOR", "1")
        .args(["info", "github-mcp"])
        .assert()
        .success()
        // Human output is on stderr (stdout stays machine-clean).
        .stderr(predicate::str::contains("87/100"))
        .stderr(predicate::str::contains("Green"))
        .stderr(predicate::str::contains("SS-MCP-POISON-UNICODE-TAG-01"))
        .stderr(predicate::str::contains("Report:"))
        .stdout(predicate::str::is_empty());
}

#[test]
fn info_typo_prints_did_you_mean_and_exits_3() {
    let tmp = tempfile::tempdir().unwrap();
    let server = mock_api();
    cli(tmp.path())
        .env("SAFERSKILLS_API_URL", server.url())
        .env("NO_COLOR", "1")
        .args(["info", "ghub-mcp"])
        .assert()
        .code(3)
        .stderr(predicate::str::contains("Did you mean"))
        .stderr(predicate::str::contains("saferskills scan <github-url>"));
}

#[test]
fn no_color_strips_ansi() {
    let tmp = tempfile::tempdir().unwrap();
    let server = mock_api();
    let output = cli(tmp.path())
        .env("SAFERSKILLS_API_URL", server.url())
        .args(["--no-color", "info", "github-mcp"])
        .assert()
        .success()
        .get_output()
        .stderr
        .clone();
    let text = String::from_utf8_lossy(&output);
    assert!(
        !text.contains('\u{1b}'),
        "no ANSI escape with --no-color: {text:?}"
    );
}

#[test]
fn completion_emits_script() {
    let tmp = tempfile::tempdir().unwrap();
    cli(tmp.path())
        .args(["completion", "bash"])
        .assert()
        .success()
        .stdout(predicate::str::contains("saferskills"));
}

#[test]
fn man_emits_troff() {
    let tmp = tempfile::tempdir().unwrap();
    cli(tmp.path())
        .arg("man")
        .assert()
        .success()
        .stdout(predicate::str::contains(".TH"));
}

#[test]
fn scan_missing_path_is_a_target_error() {
    // A non-existent local target fails fast with a target error (SS-E-1603)
    // BEFORE any network.
    let tmp = tempfile::tempdir().unwrap();
    cli(tmp.path())
        .args(["scan", "./definitely-not-a-real-path-xyz"])
        .assert()
        .failure()
        .stderr(predicate::str::contains("SS-E-1603"));
}

#[test]
fn scan_with_no_target_audits_local() {
    // `scan` with no target routes to a local audit (D-05-27) — it enumerates
    // capabilities installed across detected agents (no longer the CLI's install
    // ledger). We assert only the routing preamble: the audit outcome depends on
    // what is actually installed on the host, and the full enumerate → bundle →
    // upload → report chain is covered against a mock in tests/scan_cli.rs.
    let tmp = tempfile::tempdir().unwrap();
    cli(tmp.path())
        .arg("scan")
        .assert()
        .stderr(predicate::str::contains("auditing installed capabilities"));
}

#[test]
fn no_subcommand_prints_help_and_succeeds() {
    let tmp = tempfile::tempdir().unwrap();
    cli(tmp.path())
        .assert()
        .success()
        .stdout(predicate::str::contains("Usage"));
}
