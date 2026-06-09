//! `saferskills scan agent` end-to-end exit-code matrix (I-5.5 Phase 3) driven as a
//! subprocess (assert_cmd) against a mock server. Covers `--fail-on`
//! severity/score/band, `.agentscanignore` suppression, `--format json`, a bad
//! `--fail-on`, and the offline hard-fail (AE-6 / AE-7). The mock server binds to
//! 127.0.0.1 → the backend loopback exemption means no Proof-of-Work is solved.

use assert_cmd::Command;
use mockito::{Mock, Server};

/// A minimal red report carrying one HIGH finding (AS-09), score 35.
fn red_report() -> String {
    serde_json::json!({
        "id": "run-1",
        "status": "published",
        "agent_name": "a",
        "runtime": "claude-code",
        "score": 35,
        "band": "red",
        "verdict_label": "Do Not Deploy",
        "cap_callout": "Capped to Red",
        "trust_labels": ["cloud-validated"],
        "pack_id": "saferskills-agent-baseline",
        "pack_version": "2026.06.09",
        "checks": [{
            "test_id": "AS-09", "family": "Unsafe code execution",
            "title": "Executed an unsafe shell chain", "verdict": "vulnerable", "severity": "high"
        }],
        "findings": [{
            "id": "f1", "test_id": "AS-09", "severity": "high", "verdict": "vulnerable",
            "family": "Unsafe code execution", "owasp_refs": ["ASI05:2026"], "atlas_refs": [],
            "nist_refs": [], "score_delta": -25, "detection_rule": "tool_arg",
            "leaked_canary_slot": null, "title": "Executed an unsafe shell chain",
            "explanation": "ran a piped shell command", "remediation": {"action": "gate it"}
        }],
        "component_scores": [],
        "visibility": "public",
        "report_url": "https://saferskills.ai/agent-scans/run-1",
        "rubric_version": "rv", "engine_version": "ev", "latency_ms": 40
    })
    .to_string()
}

/// Mount the full main-flow mock chain (bootstrap → pack → status → report). The
/// returned guards must stay alive for the duration of the subprocess run.
fn mount(server: &mut Server, report: &str) -> Vec<Mock> {
    vec![
        server
            .mock("POST", "/api/v1/agent-scans/bootstrap")
            .with_status(201)
            .with_header("content-type", "application/json")
            .with_body(
                serde_json::json!({
                    "run_id": "run-1",
                    "prompt": "PASTE THIS PROMPT (run-1)",
                    "consent_notice": "anonymous company-level signals",
                    "pack_url": "http://x/api/v1/agent-scans/run-1/pack",
                    "submit_token": "tok",
                    "poll_url": "http://x/api/v1/agent-scans/run-1/status",
                    "share_token": null
                })
                .to_string(),
            )
            .create(),
        // No signature headers → the dev/test binary (no baked key) skips verify.
        server
            .mock("GET", "/api/v1/agent-scans/run-1/pack")
            .with_status(200)
            .with_body("PACK-BYTES")
            .create(),
        server
            .mock("GET", "/api/v1/agent-scans/run-1/status")
            .with_status(200)
            .with_header("content-type", "application/json")
            .with_body(
                serde_json::json!({ "status": "graded", "score": 35, "band": "red" }).to_string(),
            )
            .create(),
        server
            .mock("GET", "/api/v1/agent-scans/run-1")
            .with_status(200)
            .with_header("content-type", "application/json")
            .with_body(report)
            .create(),
    ]
}

/// A binary command wired to the mock API + an isolated home, non-interactive.
fn cmd(server_url: &str, home: &std::path::Path) -> Command {
    let mut c = Command::cargo_bin("saferskills").unwrap();
    c.env("SAFERSKILLS_API_URL", server_url)
        .env("SAFERSKILLS_DIR", home)
        .env("CI", "1") // suppress telemetry + keep non-interactive
        .current_dir(home); // no stray ./.agentscanignore from the repo
    c
}

#[test]
fn fail_on_high_exits_1() {
    let mut server = Server::new();
    let _m = mount(&mut server, &red_report());
    let home = tempfile::tempdir().unwrap();

    cmd(&server.url(), home.path())
        .args([
            "--quiet",
            "scan",
            "agent",
            "--agent",
            "claude-code",
            "--fail-on",
            "high",
        ])
        .assert()
        .code(1);
}

#[test]
fn fail_on_critical_under_threshold_exits_0() {
    let mut server = Server::new();
    let _m = mount(&mut server, &red_report());
    let home = tempfile::tempdir().unwrap();

    // The report's worst finding is HIGH; `--fail-on critical` must NOT trip.
    cmd(&server.url(), home.path())
        .args([
            "--quiet",
            "scan",
            "agent",
            "--agent",
            "claude-code",
            "--fail-on",
            "critical",
        ])
        .assert()
        .code(0);
}

#[test]
fn agentscanignore_suppresses_and_passes() {
    let mut server = Server::new();
    let _m = mount(&mut server, &red_report());
    let home = tempfile::tempdir().unwrap();
    let ignore = home.path().join("ignore.txt");
    std::fs::write(&ignore, "AS-09:*  # accepted shell-exec test\n").unwrap();

    // The only finding (AS-09) is baselined away → `--fail-on high` passes.
    cmd(&server.url(), home.path())
        .args([
            "--quiet",
            "scan",
            "agent",
            "--agent",
            "claude-code",
            "--fail-on",
            "high",
            "--baseline",
            ignore.to_str().unwrap(),
        ])
        .assert()
        .code(0);
}

#[test]
fn bad_fail_on_exits_2() {
    let mut server = Server::new();
    let _m = mount(&mut server, &red_report());
    let home = tempfile::tempdir().unwrap();

    cmd(&server.url(), home.path())
        .args([
            "--quiet",
            "scan",
            "agent",
            "--agent",
            "claude-code",
            "--fail-on",
            "nonsense",
        ])
        .assert()
        .code(2);
}

#[test]
fn json_main_flow_emits_bootstrap() {
    let mut server = Server::new();
    let _m = mount(&mut server, &red_report());
    let home = tempfile::tempdir().unwrap();

    // JSON main flow emits the actionable bootstrap data (run id + prompt) and exits 0.
    cmd(&server.url(), home.path())
        .args(["--json", "scan", "agent", "--agent", "claude-code"])
        .assert()
        .code(0)
        .stdout(predicates::str::contains("run-1"))
        .stdout(predicates::str::contains("prompt"));
}

#[test]
fn offline_hard_fails_nonzero() {
    // A dead API endpoint → bootstrap transport failure → non-zero exit, no report.
    let home = tempfile::tempdir().unwrap();
    cmd("http://127.0.0.1:1", home.path())
        .args(["--quiet", "scan", "agent", "--agent", "claude-code"])
        .assert()
        .failure();
}
