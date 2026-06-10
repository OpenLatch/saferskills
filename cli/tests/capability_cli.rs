//! Subprocess coverage for the `capability` command (D-05-26/27) through the real
//! binary against a mock API. Cross-platform: `capability` needs no detected agent,
//! so unlike the lifecycle test this runs everywhere (and exercises the PoW solve →
//! submit → poll chain end-to-end via `run_capability`/`scan_url`/`scan_path`/
//! `run_local_audit`/`obtain_pow`/`print_run_report`).

use assert_cmd::Command;
use mockito::{Matcher, Server, ServerGuard};
use predicates::prelude::*;

const SLUG: &str = "acme--gh--github-mcp";

fn run_report(run_id: &str) -> serde_json::Value {
    serde_json::json!({
        "id": run_id,
        "github_url": "https://github.com/acme/widget",
        "repo_aggregate_score": 88,
        "repo_tier": "green",
        "kind_tally": { "mcp_server": 1 },
        "capability_count": 1,
        "status": "completed",
        "capabilities": [{
            "kind": "mcp_server",
            "name": "github-mcp",
            "aggregate_score": 88,
            "tier": "green",
            "scan_id": "scan-1",
            "catalog_slug": SLUG,
            "findings": []
        }]
    })
}

/// Mock the full CLI scan-submit surface: PoW challenge, both submit endpoints,
/// the run poll, and the catalog reads the no-target `capability` audit needs.
fn mock_scan_api() -> ServerGuard {
    let mut server = Server::new();
    // Low difficulty so the CLI solves the PoW near-instantly.
    server
        .mock("GET", "/api/v1/scans/cli-challenge")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            serde_json::json!({ "challenge": "cGF5bG9hZA==.deadbeefmac", "difficulty": 4, "expires_at": "2030-01-01T00:00:00Z" })
                .to_string(),
        )
        .expect_at_least(1)
        .create();
    server
        .mock("POST", "/api/v1/scans")
        .with_status(202)
        .with_header("content-type", "application/json")
        .with_body(serde_json::json!({ "id": "run-1", "status": "pending" }).to_string())
        .expect_at_least(1)
        .create();
    server
        .mock("POST", "/api/v1/scans/upload")
        .with_status(202)
        .with_header("content-type", "application/json")
        .with_body(
            serde_json::json!({ "id": "run-2", "status": "pending", "source_kind": "upload" })
                .to_string(),
        )
        .expect_at_least(1)
        .create();
    server
        .mock(
            "GET",
            Matcher::Regex(r"^/api/v1/scans/runs/run-\d".to_string()),
        )
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(run_report("run-1").to_string())
        .expect_at_least(1)
        .create();
    // For the no-target `capability` audit slug → github_url resolution.
    server
        .mock("GET", format!("/api/v1/items/{SLUG}").as_str())
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            serde_json::json!({
                "item": {
                    "id": "id-1", "slug": SLUG, "kind": "mcp_server", "display_name": "github-mcp",
                    "github_url": "https://github.com/acme/widget", "popularity_tier": "emerging",
                    "registries": [], "agent_compatibility": []
                }
            })
            .to_string(),
        )
        .expect_at_least(0)
        .create();
    server
}

fn cli(ss_dir: &std::path::Path, api: &str) -> Command {
    let mut cmd = Command::cargo_bin("saferskills").unwrap();
    cmd.env("SAFERSKILLS_DIR", ss_dir)
        .env("SAFERSKILLS_API_URL", api)
        .env("CI", "1")
        .env("NO_COLOR", "1");
    cmd
}

#[test]
fn capability_github_url_public_reports_run() {
    let ss = tempfile::tempdir().unwrap();
    let server = mock_scan_api();
    let out = cli(ss.path(), &server.url())
        .args(["--json", "capability", "https://github.com/acme/widget"])
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let v: serde_json::Value = serde_json::from_slice(&out).expect("scan json");
    assert_eq!(v["run_id"], "run-1");
    assert_eq!(v["score"], 88);
    assert!(v["report_url"].as_str().unwrap().contains("/scans/run-1"));
}

#[test]
fn capability_local_path_uploads_and_reports() {
    let ss = tempfile::tempdir().unwrap();
    let target = tempfile::tempdir().unwrap();
    std::fs::write(target.path().join("SKILL.md"), b"---\nname: t\n---\n# t\n").unwrap();
    let server = mock_scan_api();
    let out = cli(ss.path(), &server.url())
        .args(["--json", "capability", target.path().to_str().unwrap()])
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    // The upload (run-2) submit → poll → report chain completed (the shared mock
    // run report echoes score 88; its id field is fixed, so assert on the score).
    let v: serde_json::Value = serde_json::from_slice(&out).expect("scan json");
    assert_eq!(v["score"], 88);
}

#[test]
fn capability_missing_target_errors() {
    let ss = tempfile::tempdir().unwrap();
    let server = mock_scan_api();
    cli(ss.path(), &server.url())
        .args(["capability", "./definitely-not-here-xyz"])
        .assert()
        .failure()
        .stderr(predicate::str::contains("SS-E-1603"));
}

/// `capability` (no target) now enumerates capabilities installed across detected
/// agents (D-05-27) instead of the CLI's own install ledger. With an empty HOME no
/// agents are detected, so the audit short-circuits to the empty machine shape
/// `{"run_id":null,"capabilities":[],"skipped":[]}` (exit 0).
///
/// The populated path (a real agent config on disk) is covered by the
/// `agents::enumerate` unit tests — the same fake-HOME limitation as `detect.rs`
/// prevents driving the real binary against synthetic agents.
#[test]
fn capability_audit_empty_when_no_agents() {
    let ss = tempfile::tempdir().unwrap();
    let fake_home = tempfile::tempdir().unwrap();
    let server = mock_scan_api();
    let out = cli(ss.path(), &server.url())
        // Point HOME / config base at an empty dir so no agent is detected.
        .env("HOME", fake_home.path())
        .env("USERPROFILE", fake_home.path())
        .env("XDG_CONFIG_HOME", fake_home.path().join(".config"))
        .args(["--json", "capability"])
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let v: serde_json::Value = serde_json::from_slice(&out).expect("capability audit json");
    // The contract keys are always present; an empty HOME yields the empty shape.
    assert!(v.get("run_id").is_some());
    assert!(v["capabilities"].is_array());
    assert!(v["skipped"].is_array());
    if v["run_id"].is_null() {
        assert_eq!(v["capabilities"].as_array().unwrap().len(), 0);
    }
}
