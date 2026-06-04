//! Offline finding-prose cache (D-05-32).
//!
//! The CLI renders findings with their human title/explanation/remediation by
//! fetching `GET /api/v1/rubric/content` once and caching it under
//! `~/.saferskills/cache/rules-content.<rubricSha>.json`. It refetches only when
//! the version it needs (a scan report's `rubric_version`) isn't already cached.
//!
//! **Fail-open**: any fetch/cache error degrades to an empty map — the install
//! never blocks on finding prose; the finding still shows its `rule_id` +
//! `remediation_link`.

use std::path::PathBuf;

use crate::api::dto::RubricContent;
use crate::api::Api;
use crate::core::config::{atomic_write, cache_dir};

fn cache_path(version: &str) -> PathBuf {
    // Sanitize the version into a safe filename segment (a git tree SHA is
    // already `[0-9a-f]`, but never trust it blindly).
    let safe: String = version
        .chars()
        .map(|c| if c.is_ascii_alphanumeric() { c } else { '_' })
        .take(64)
        .collect();
    cache_dir().join(format!("rules-content.{safe}.json"))
}

/// Load the rule-content map for the wanted `rubric_version`.
///
/// 1. If a cache file for `want_version` exists + parses → use it (no network).
/// 2. Else fetch `GET /rubric/content`, cache it keyed by the *returned*
///    version, and return it.
/// 3. On any error → an empty [`RubricContent`] (fail-open).
///
/// `want_version` is the `rubric_version` carried on the scan report; pass `None`
/// to always fetch the latest.
pub async fn load_or_fetch(api: &Api, want_version: Option<&str>) -> RubricContent {
    if let Some(version) = want_version {
        if let Some(cached) = read_cache(version) {
            return cached;
        }
    }
    match api.get_rubric_content().await {
        Ok(content) => {
            // Best-effort cache write keyed by the authoritative returned version.
            if !content.rubric_version.is_empty() {
                if let Ok(bytes) = serde_json::to_vec(&content) {
                    let _ = atomic_write(&cache_path(&content.rubric_version), &bytes);
                }
            }
            content
        }
        Err(_) => RubricContent::default(),
    }
}

fn read_cache(version: &str) -> Option<RubricContent> {
    let raw = std::fs::read_to_string(cache_path(version)).ok()?;
    serde_json::from_str(&raw).ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cache_path_sanitizes_version() {
        let p = cache_path("abc123/../etc");
        let name = p.file_name().unwrap().to_string_lossy();
        assert!(!name.contains(".."));
        assert!(!name.contains('/'));
        assert!(name.starts_with("rules-content."));
    }

    #[test]
    fn read_cache_roundtrip() {
        let dir = tempfile::tempdir().unwrap();
        // SAFETY: single-threaded test; the override is process-local.
        std::env::set_var("SAFERSKILLS_DIR", dir.path());
        let content = RubricContent {
            rubric_version: "deadbeef".into(),
            rules: Default::default(),
        };
        let bytes = serde_json::to_vec(&content).unwrap();
        atomic_write(&cache_path("deadbeef"), &bytes).unwrap();
        let back = read_cache("deadbeef").expect("cache hit");
        assert_eq!(back.rubric_version, "deadbeef");
        assert!(read_cache("missing").is_none());
        std::env::remove_var("SAFERSKILLS_DIR");
    }
}
