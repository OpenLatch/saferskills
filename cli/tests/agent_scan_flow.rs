//! Agent-scan API-surface happy paths (I-5.5 Phase 3) driven against a mock server.
//!
//! Exercises bootstrap → token-gated pack fetch (with the signature headers) → poll
//! `/status` → submit a paste-back blob → report, through the typed `Api` surface (no
//! subprocess; named `agent_scan_flow` to dodge the Windows os-error-740 elevation
//! quirk that bites `*install*`/`*update*`/`*setup*` binary names). The CLI's own
//! `verify_strict` tamper path is unit-tested in `commands::agent_scan` (no baked key
//! in the dev/test binary, so the integration path skips verification by design).

use std::time::Duration;

use mockito::Server;
use saferskills::api::dto::Tier;
use saferskills::api::Api;
use saferskills::cli::output::{OutputConfig, OutputFormat};

fn quiet_output() -> OutputConfig {
    OutputConfig {
        format: OutputFormat::Json,
        verbose: false,
        quiet: true,
        color: false,
    }
}

/// A minimal but schema-faithful `AgentScanReport` body.
fn report_body(band: &str, score: u8) -> String {
    serde_json::json!({
        "id": "run-1",
        "status": "published",
        "agent_name": "a",
        "runtime": "claude-code",
        "score": score,
        "band": band,
        "verdict_label": "Do Not Deploy",
        "trust_labels": ["cloud-validated", "client-administered"],
        "pack_id": "saferskills-agent-baseline",
        "pack_version": "2026.06.09",
        "checks": [],
        "findings": [{
            "id": "f1",
            "test_id": "AS-09",
            "severity": "high",
            "verdict": "vulnerable",
            "family": "Unsafe code execution",
            "owasp_refs": ["ASI05:2026"],
            "atlas_refs": [],
            "nist_refs": [],
            "score_delta": -25,
            "detection_rule": "tool_arg",
            "leaked_canary_slot": null,
            "title": "Executed an unsafe shell chain",
            "explanation": "ran a piped shell command",
            "remediation": {"action": "gate code execution"}
        }],
        "component_scores": [],
        "visibility": "public",
        "report_url": "https://saferskills.ai/agent-scans/run-1",
        "rubric_version": "rv",
        "engine_version": "ev",
        "latency_ms": 40
    })
    .to_string()
}

#[tokio::test]
async fn bootstrap_returns_prompt_and_token() {
    let mut server = Server::new_async().await;
    server
        .mock("POST", "/api/v1/agent-scans/bootstrap")
        .with_status(201)
        .with_header("content-type", "application/json")
        .with_body(
            serde_json::json!({
                "run_id": "run-1",
                "prompt": "Run id: run-1 token: tok",
                "consent_notice": "anonymous company-level signals",
                "pack_url": "https://saferskills.ai/api/v1/agent-scans/run-1/pack",
                "submit_token": "tok",
                "poll_url": "https://saferskills.ai/api/v1/agent-scans/run-1/status",
                "share_token": null
            })
            .to_string(),
        )
        .create_async()
        .await;

    let api = Api::new(server.url()).unwrap();
    let boot = api
        .bootstrap_agent_scan(
            "claude-code",
            "my-agent",
            "claude-code",
            "public",
            None,
            None,
            "",
        )
        .await
        .unwrap();
    assert_eq!(boot.run_id, "run-1");
    assert_eq!(boot.submit_token, "tok");
    assert!(boot.share_token.is_none());
}

#[tokio::test]
async fn get_pack_bytes_returns_signature_headers() {
    let mut server = Server::new_async().await;
    server
        .mock("GET", "/api/v1/agent-scans/run-1/pack")
        .match_header("x-agent-run-token", "tok")
        .with_status(200)
        .with_header("X-Pack-Key-Id", "saferskills-agent-pack-2026")
        .with_header("X-Pack-Signature", "c2lnbmF0dXJl")
        .with_body("THE-EXACT-PACK-BYTES")
        .create_async()
        .await;

    let api = Api::new(server.url()).unwrap();
    let (body, key_id, sig) = api.get_pack_bytes("run-1", "tok").await.unwrap();
    assert_eq!(body, b"THE-EXACT-PACK-BYTES");
    assert_eq!(key_id.as_deref(), Some("saferskills-agent-pack-2026"));
    assert_eq!(sig.as_deref(), Some("c2lnbmF0dXJl"));
}

#[tokio::test]
async fn pack_fetch_without_token_is_rejected() {
    let mut server = Server::new_async().await;
    server
        .mock("GET", "/api/v1/agent-scans/run-1/pack")
        .with_status(403)
        .with_body(serde_json::json!({ "error": "bad_run_token" }).to_string())
        .create_async()
        .await;
    let api = Api::new(server.url()).unwrap();
    let err = api.get_pack_bytes("run-1", "tok").await.unwrap_err();
    // 403 is mapped to a clear gate/token error (not a generic API status).
    assert_eq!(err.code, "SS-E-1600");
}

#[tokio::test]
async fn wait_for_agent_run_polls_to_graded() {
    let mut server = Server::new_async().await;
    server
        .mock("GET", "/api/v1/agent-scans/run-1/status")
        .match_header("x-agent-run-token", "tok")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            serde_json::json!({ "status": "graded", "score": 35, "band": "red" }).to_string(),
        )
        .create_async()
        .await;

    let api = Api::new(server.url()).unwrap();
    let status = api
        .wait_for_agent_run("run-1", "tok", &quiet_output(), Duration::from_secs(5))
        .await
        .unwrap();
    assert_eq!(status.status, "graded");
    assert_eq!(status.score, Some(35));
}

#[tokio::test]
async fn wait_for_agent_run_tolerates_transient_failure() {
    // Regression: a SINGLE transient poll error (here a 503 while the API is busy)
    // used to abort the whole wait with SS-E-1100, even though the run completes
    // fine server-side. The resilient poll must ride the blip and still return the
    // graded status. `.expect(1)` exhausts the 503 mock after one hit, so the next
    // poll (1.5s later) matches the graded mock.
    let mut server = Server::new_async().await;
    server
        .mock("GET", "/api/v1/agent-scans/run-1/status")
        .with_status(503)
        .expect(1)
        .create_async()
        .await;
    server
        .mock("GET", "/api/v1/agent-scans/run-1/status")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            serde_json::json!({ "status": "graded", "score": 100, "band": "green" }).to_string(),
        )
        .create_async()
        .await;

    let api = Api::new(server.url()).unwrap();
    let status = api
        .wait_for_agent_run("run-1", "tok", &quiet_output(), Duration::from_secs(15))
        .await
        .expect("a transient 503 must not abort the poll");
    assert_eq!(status.status, "graded");
    assert_eq!(status.score, Some(100));
}

#[tokio::test]
async fn submit_agent_blob_returns_report() {
    let mut server = Server::new_async().await;
    server
        .mock("POST", "/api/v1/agent-scans/run-1/submit")
        .match_header("x-agent-run-token", "tok")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(report_body("red", 35))
        .create_async()
        .await;

    let api = Api::new(server.url()).unwrap();
    let report = api
        .submit_agent_blob("run-1", "tok", "PASTE-BACK-BLOB".to_string(), "", false)
        .await
        .unwrap();
    assert_eq!(report.band, Tier::Red);
    assert_eq!(report.findings.len(), 1);
    assert_eq!(report.findings[0].test_id, "AS-09");
}
