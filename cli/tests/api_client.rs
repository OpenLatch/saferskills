//! In-process tests for the typed API surface + HTTP client (no subprocess —
//! these drive `saferskills::api::Api` directly against a mock server, so the
//! `core::http` error-mapping + `api::resolve` paths are covered on every
//! platform regardless of subprocess-coverage merging).

use mockito::{Matcher, Server};
use saferskills::api::Api;

fn item(slug: &str, display: &str) -> serde_json::Value {
    serde_json::json!({
        "id": "id-1",
        "slug": slug,
        "kind": "mcp_server",
        "display_name": display,
        "popularity_tier": "emerging",
        "latest_scan_score": 87,
        "latest_scan_tier": "green",
        "updated_at": "2026-06-01T00:00:00Z"
    })
}

#[tokio::test]
async fn resolve_exact_match() {
    let mut server = Server::new_async().await;
    server
        .mock("GET", "/api/v1/items")
        .match_query(Matcher::Any)
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            serde_json::json!({ "data": [item("a--b--mcp-server-x", "github-mcp")] }).to_string(),
        )
        .create_async()
        .await;

    let api = Api::new(server.url()).unwrap();
    let resolved = api.resolve("github-mcp").await.unwrap();
    assert_eq!(resolved.display_name, "github-mcp");
}

#[tokio::test]
async fn resolve_typo_returns_not_found_with_suggestion() {
    let mut server = Server::new_async().await;
    server
        .mock("GET", "/api/v1/items")
        .match_query(Matcher::Any)
        .with_status(200)
        .with_body(
            serde_json::json!({ "data": [item("a--b--mcp-server-github", "github-mcp")] })
                .to_string(),
        )
        .create_async()
        .await;

    let api = Api::new(server.url()).unwrap();
    let err = api.resolve("ghub-mcp").await.unwrap_err();
    assert_eq!(err.exit_code(), 3);
    assert!(err.suggestion.unwrap().contains("Did you mean"));
}

#[tokio::test]
async fn resolve_empty_returns_not_found() {
    let mut server = Server::new_async().await;
    server
        .mock("GET", "/api/v1/items")
        .match_query(Matcher::Any)
        .with_status(200)
        .with_body(serde_json::json!({ "data": [] }).to_string())
        .create_async()
        .await;

    let api = Api::new(server.url()).unwrap();
    let err = api.resolve("nothing").await.unwrap_err();
    assert_eq!(err.code, "SS-E-1200");
}

#[tokio::test]
async fn get_item_404_maps_to_not_found() {
    let mut server = Server::new_async().await;
    server
        .mock("GET", "/api/v1/items/missing")
        .with_status(404)
        .create_async()
        .await;

    let api = Api::new(server.url()).unwrap();
    let err = api.get_item("missing").await.unwrap_err();
    assert_eq!(err.exit_code(), 3);
}

#[tokio::test]
async fn server_500_maps_to_api_status() {
    let mut server = Server::new_async().await;
    server
        .mock("GET", "/api/v1/items/x")
        .with_status(500)
        .create_async()
        .await;

    let api = Api::new(server.url()).unwrap();
    let err = api.get_item("x").await.unwrap_err();
    assert_eq!(err.code, "SS-E-1101");
    assert_eq!(err.exit_code(), 6);
}

#[tokio::test]
async fn rate_limited_429_maps_to_rate_limit() {
    let mut server = Server::new_async().await;
    server
        .mock("GET", "/api/v1/items/x")
        .with_status(429)
        .create_async()
        .await;

    let api = Api::new(server.url()).unwrap();
    let err = api.get_item("x").await.unwrap_err();
    assert_eq!(err.code, "SS-E-1102");
}

#[tokio::test]
async fn malformed_body_maps_to_decode_error() {
    let mut server = Server::new_async().await;
    server
        .mock("GET", "/api/v1/items/x")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body("{ not json")
        .create_async()
        .await;

    let api = Api::new(server.url()).unwrap();
    let err = api.get_item("x").await.unwrap_err();
    assert_eq!(err.code, "SS-E-1103");
}

#[tokio::test]
async fn health_deserializes() {
    let mut server = Server::new_async().await;
    server
        .mock("GET", "/api/v1/health")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(serde_json::json!({ "status": "ok", "version": "1.0", "git_sha": "abc", "migrations_ok": true }).to_string())
        .create_async()
        .await;

    let api = Api::new(server.url()).unwrap();
    let health = api.health().await.unwrap();
    assert_eq!(health.status, "ok");
    assert!(health.migrations_ok);
    assert_eq!(api.base(), server.url().trim_end_matches('/'));
}

#[tokio::test]
async fn get_run_deserializes_roll_up() {
    let mut server = Server::new_async().await;
    server
        .mock("GET", "/api/v1/scans/runs/run-1")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            serde_json::json!({
                "id": "run-1",
                "repo_aggregate_score": 80,
                "repo_tier": "green",
                "capabilities": []
            })
            .to_string(),
        )
        .create_async()
        .await;

    let api = Api::new(server.url()).unwrap();
    let run = api.get_run("run-1").await.unwrap();
    assert_eq!(run.repo_aggregate_score, 80);
}
