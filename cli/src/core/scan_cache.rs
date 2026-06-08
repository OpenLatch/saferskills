//! The local scan-results cache — `~/.saferskills/scan_cache.json`.
//!
//! `scan --local` persists each scored capability here, keyed by a CLI-side
//! content hash ([`crate::agents::enumerate::LocalCapability::content_hash`]), so
//! `list` can show a score for a capability that was previously scanned even
//! though it was never installed via the CLI. It is **drift-aware**: editing a
//! capability's files re-hashes → cache miss → the capability is correctly shown
//! "not scanned" again.
//!
//! Mirrors [`crate::core::registry`]: the same atomic read/write contract and the
//! same `SS-E-1002` corrupt-file handling. Growth is bounded — [`upsert`] drops
//! entries older than [`MAX_AGE_DAYS`] so the file cannot grow unbounded across
//! machine churn.

use std::collections::HashMap;
use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::api::dto::Tier;
use crate::core::config::{atomic_write, scan_cache_path};
use crate::core::error::{SsError, ERR_STATE_CORRUPT};

/// Retention cap — a cached entry older than this is dropped on the next
/// [`upsert`] (so a re-imaged machine or a stale capability never accumulates).
const MAX_AGE_DAYS: i64 = 90;

/// One previously-scanned capability's result, keyed by its CLI-side content
/// hash so `list` can re-attach the score to the same bytes on disk.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CachedScan {
    /// Join key ← [`crate::agents::enumerate::LocalCapability::content_hash`].
    pub content_hash: String,
    /// Backend snake_case kind (`skill` | `mcp_server` | …).
    pub kind: String,
    /// Display name.
    pub name: String,
    /// Catalog slug the scan landed under.
    pub catalog_slug: String,
    /// Aggregate score (0–100).
    pub score: u8,
    /// Score tier.
    pub tier: Tier,
    /// When the scan completed.
    pub scanned_at: chrono::DateTime<chrono::Utc>,
    /// Public report URL, when known.
    #[serde(default)]
    pub report_url: Option<String>,
}

/// Load the scan cache, returning an empty list when the file is absent. A
/// present-but-corrupt file is `SS-E-1002` (never silently dropped — but, unlike
/// the install registry, the cache is reconstructable by re-scanning, so the
/// suggestion points at a safe delete).
pub fn load() -> Result<Vec<CachedScan>, SsError> {
    load_from(&scan_cache_path())
}

fn load_from(path: &Path) -> Result<Vec<CachedScan>, SsError> {
    let raw = match std::fs::read_to_string(path) {
        Ok(s) => s,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(e) => {
            return Err(SsError::new(
                ERR_STATE_CORRUPT,
                format!("Failed to read {}: {e}", path.display()),
            ))
        }
    };
    if raw.trim().is_empty() {
        return Ok(Vec::new());
    }
    serde_json::from_str(&raw).map_err(|e| {
        SsError::new(
            ERR_STATE_CORRUPT,
            format!("scan_cache.json is corrupt: {e}"),
        )
        .with_suggestion(
            "Delete ~/.saferskills/scan_cache.json — it is rebuilt by `saferskills scan --local`.",
        )
    })
}

/// Atomically persist the cache (temp → fsync → rename).
pub fn save(entries: &[CachedScan]) -> Result<(), SsError> {
    save_to(&scan_cache_path(), entries)
}

fn save_to(path: &Path, entries: &[CachedScan]) -> Result<(), SsError> {
    let json = serde_json::to_vec_pretty(entries).map_err(|e| {
        SsError::new(
            ERR_STATE_CORRUPT,
            format!("Failed to serialize scan cache: {e}"),
        )
    })?;
    atomic_write(path, &json)
}

/// Merge `entries` into the on-disk cache (newest `scanned_at` per content hash
/// wins), drop entries older than [`MAX_AGE_DAYS`], and persist. Best-effort at
/// the call site — a failure here never fails a scan.
pub fn upsert(entries: Vec<CachedScan>) -> Result<(), SsError> {
    let merged = merge_entries(load()?, entries, chrono::Utc::now());
    save(&merged)
}

/// Pure merge: union `existing` + `new` keyed by `content_hash` (latest
/// `scanned_at` wins; on a tie the newly-supplied entry wins), drop anything
/// older than [`MAX_AGE_DAYS`] relative to `now`, and return sorted by hash for
/// a byte-stable file.
fn merge_entries(
    existing: Vec<CachedScan>,
    new: Vec<CachedScan>,
    now: chrono::DateTime<chrono::Utc>,
) -> Vec<CachedScan> {
    let mut by_hash: HashMap<String, CachedScan> = HashMap::new();
    // `existing` first, then `new`, so a new entry wins on an equal timestamp.
    for e in existing.into_iter().chain(new.into_iter()) {
        match by_hash.get(&e.content_hash) {
            Some(prev) if prev.scanned_at > e.scanned_at => {}
            _ => {
                by_hash.insert(e.content_hash.clone(), e);
            }
        }
    }
    let cutoff = now - chrono::Duration::days(MAX_AGE_DAYS);
    let mut kept: Vec<CachedScan> = by_hash
        .into_values()
        .filter(|e| e.scanned_at >= cutoff)
        .collect();
    kept.sort_by(|a, b| a.content_hash.cmp(&b.content_hash));
    kept
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entry(hash: &str, score: u8, age_days: i64) -> CachedScan {
        CachedScan {
            content_hash: hash.into(),
            kind: "skill".into(),
            name: "demo".into(),
            catalog_slug: "upload--abcd1234--skill-demo".into(),
            score,
            tier: Tier::Green,
            scanned_at: chrono::DateTime::from_timestamp(0, 0).unwrap()
                + chrono::Duration::days(age_days),
            report_url: None,
        }
    }

    #[test]
    fn load_absent_is_empty() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("scan_cache.json");
        assert!(load_from(&path).unwrap().is_empty());
    }

    #[test]
    fn save_then_load_roundtrips() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("scan_cache.json");
        let want = vec![entry("a", 91, 0)];
        save_to(&path, &want).unwrap();
        let got = load_from(&path).unwrap();
        assert_eq!(got.len(), 1);
        assert_eq!(got[0].content_hash, "a");
        assert_eq!(got[0].score, 91);
    }

    #[test]
    fn corrupt_cache_is_an_error() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("scan_cache.json");
        std::fs::write(&path, b"{not json").unwrap();
        let err = load_from(&path).unwrap_err();
        assert_eq!(err.code, ERR_STATE_CORRUPT);
    }

    #[test]
    fn merge_keeps_newest_per_hash() {
        let now = chrono::DateTime::from_timestamp(0, 0).unwrap() + chrono::Duration::days(10);
        // Same hash, an older (day 1) and a newer (day 5) scan → newer wins.
        let merged = merge_entries(vec![entry("h", 40, 1)], vec![entry("h", 88, 5)], now);
        assert_eq!(merged.len(), 1);
        assert_eq!(merged[0].score, 88);
    }

    #[test]
    fn merge_drops_aged_out_entries() {
        // `now` is day 200; a day-0 entry is >90 days old → dropped; day-150 kept.
        let now = chrono::DateTime::from_timestamp(0, 0).unwrap() + chrono::Duration::days(200);
        let merged = merge_entries(
            vec![entry("old", 50, 0), entry("fresh", 70, 150)],
            vec![],
            now,
        );
        assert_eq!(merged.len(), 1);
        assert_eq!(merged[0].content_hash, "fresh");
    }

    #[test]
    fn merge_is_sorted_by_hash() {
        let now = chrono::DateTime::from_timestamp(0, 0).unwrap() + chrono::Duration::days(1);
        let merged = merge_entries(
            vec![entry("c", 1, 0), entry("a", 2, 0), entry("b", 3, 0)],
            vec![],
            now,
        );
        let hashes: Vec<&str> = merged.iter().map(|e| e.content_hash.as_str()).collect();
        assert_eq!(hashes, vec!["a", "b", "c"]);
    }
}
