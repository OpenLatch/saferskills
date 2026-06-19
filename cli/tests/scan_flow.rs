//! Scan-submit happy paths driven against a mock server.
//!
//! Exercises the full challenge → solve → submit → poll chain through the typed
//! `Api` surface (no subprocess; named `scan_flow` to dodge the Windows
//! os-error-740 elevation quirk that bites `*install*`/`*update*`/`*setup*`
//! binary names). Public submits carry no `share_url`; unlisted submits do, plus
//! an `expires_at` on the run.

use mockito::{Matcher, Server};
use saferskills::api::Api;
use saferskills::cli::output::{OutputConfig, OutputFormat};
use saferskills::core::pow;

fn quiet_output() -> OutputConfig {
    OutputConfig {
        format: OutputFormat::Json,
        verbose: false,
        quiet: true,
        color: false,
    }
}

/// Stub the challenge endpoint at a trivially-solvable difficulty + solve it.
async fn solved_pow(server: &mut Server) -> String {
    server
        .mock("GET", "/api/v1/scans/cli-challenge")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            serde_json::json!({
                "challenge": "cGF5bG9hZA==.deadbeefmac",
                "difficulty": 4,
                "expires_at": "2030-01-01T00:00:00Z"
            })
            .to_string(),
        )
        .create_async()
        .await;
    let api = Api::new(server.url()).unwrap();
    let ch = api.get_cli_challenge().await.unwrap();
    let solution = pow::solve_async(ch.challenge.clone(), ch.difficulty)
        .await
        .expect("difficulty 4 is solvable");
    pow::header_value(&ch.challenge, &solution)
}

#[tokio::test]
async fn public_url_scan_has_no_share_url() {
    let mut server = Server::new_async().await;
    let pow_header = solved_pow(&mut server).await;

    server
        .mock("POST", "/api/v1/scans")
        .with_status(202)
        .with_header("content-type", "application/json")
        .with_body(
            serde_json::json!({
                "id": "run-1",
                "status": "pending",
                "cached": false,
                "rubric_version": "abc1234"
            })
            .to_string(),
        )
        .create_async()
        .await;

    let api = Api::new(server.url()).unwrap();
    let resp = api
        .submit_scan_url("https://github.com/acme/widget", "public", &pow_header)
        .await
        .unwrap();
    assert_eq!(resp.id, "run-1");
    assert!(
        resp.share_url.is_none(),
        "public submit carries no share_url"
    );
}

#[tokio::test]
async fn unlisted_url_scan_carries_share_url_and_expiry() {
    let mut server = Server::new_async().await;
    let pow_header = solved_pow(&mut server).await;

    server
        .mock("POST", "/api/v1/scans")
        .with_status(202)
        .with_header("content-type", "application/json")
        .with_body(
            serde_json::json!({
                "id": "run-2",
                "status": "pending",
                "cached": false,
                "share_url": "https://saferskills.ai/scans/r/tok123"
            })
            .to_string(),
        )
        .create_async()
        .await;
    server
        .mock("GET", "/api/v1/scans/runs/run-2")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            serde_json::json!({
                "id": "run-2",
                "repo_aggregate_score": 88,
                "repo_tier": "green",
                "capability_count": 1,
                "status": "completed",
                "visibility": "unlisted",
                "expires_at": "2026-09-01T00:00:00Z",
                "capabilities": []
            })
            .to_string(),
        )
        .create_async()
        .await;

    let api = Api::new(server.url()).unwrap();
    let resp = api
        .submit_scan_url("https://github.com/acme/widget", "unlisted", &pow_header)
        .await
        .unwrap();
    assert_eq!(
        resp.share_url.as_deref(),
        Some("https://saferskills.ai/scans/r/tok123")
    );

    let run = api
        .wait_for_run("run-2", &quiet_output(), std::time::Duration::from_secs(5))
        .await
        .unwrap();
    assert_eq!(run.status.as_deref(), Some("completed"));
    assert_eq!(run.expires_at.as_deref(), Some("2026-09-01T00:00:00Z"));
}

#[tokio::test]
async fn upload_scan_happy_path() {
    let mut server = Server::new_async().await;
    let pow_header = solved_pow(&mut server).await;

    server
        .mock("POST", "/api/v1/scans/upload")
        .match_header("content-type", Matcher::Regex("multipart/form-data".into()))
        .with_status(202)
        .with_header("content-type", "application/json")
        .with_body(
            serde_json::json!({
                "id": "run-3",
                "status": "pending",
                "source_kind": "upload",
                "visibility": "public"
            })
            .to_string(),
        )
        .create_async()
        .await;

    let api = Api::new(server.url()).unwrap();
    let resp = api
        .submit_scan_upload(
            b"PK\x03\x04 zip bytes".to_vec(),
            "skill.zip",
            "public",
            None,
            &pow_header,
        )
        .await
        .unwrap();
    assert_eq!(resp.id, "run-3");
    assert_eq!(resp.source_kind.as_deref(), Some("upload"));
    assert!(resp.share_url.is_none());
}

#[tokio::test]
async fn gate_403_maps_to_scan_submit_error() {
    let mut server = Server::new_async().await;
    let pow_header = solved_pow(&mut server).await;

    server
        .mock("POST", "/api/v1/scans")
        .with_status(403)
        .with_header("content-type", "application/json")
        .with_body(serde_json::json!({ "error": "pow_failed" }).to_string())
        .create_async()
        .await;

    let api = Api::new(server.url()).unwrap();
    let err = api
        .submit_scan_url("https://github.com/acme/widget", "public", &pow_header)
        .await
        .unwrap_err();
    assert_eq!(err.code, "SS-E-1600");
    assert!(err.message.contains("pow_failed"));
}
