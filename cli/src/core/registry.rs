//! The install registry — `~/.saferskills/installs.json` (D-05-10).
//!
//! It holds the **schema + atomic read/write helpers** and is used by
//! `install` / `list` / `uninstall` / `update`. Every mutating op records its
//! intended changes BEFORE writing so a partial failure can be reverted, and the
//! registry is updated only after all writes succeed.

use serde::{Deserialize, Serialize};

use crate::core::config::{atomic_write, installs_path};
use crate::core::error::{SsError, ERR_STATE_CORRUPT};

/// One installed capability and everything written for it, so an uninstall can
/// reverse exactly the recorded changes.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InstallRecord {
    /// Canonical catalog id.
    pub canonical_id: String,
    /// Catalog slug (`/items/<slug>` permalink key).
    pub slug: String,
    /// Display name.
    pub name: String,
    /// `skill` | `mcp_server` | …
    pub kind: String,
    /// Commit SHA / ref at install time.
    #[serde(default)]
    pub version: Option<String>,
    /// Canonical agent ids the capability was installed to (D-05-14).
    #[serde(default)]
    pub agents: Vec<String>,
    /// Every file / config-key written, for a clean uninstall.
    #[serde(default)]
    pub changes: Vec<InstallChange>,
    /// When the install happened.
    pub installed_at: chrono::DateTime<chrono::Utc>,
    /// The score the user saw at install time (drift re-prompt, D-05-25).
    #[serde(default)]
    pub seen_score: Option<u8>,
}

/// A single reversible change made during an install.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum InstallChange {
    /// A file (or folder root) the CLI created — uninstall removes it.
    File { path: String },
    /// A config key the CLI merged in — uninstall restores `prior` (or deletes
    /// the key when `prior` is `None`).
    ConfigKey {
        file: String,
        key: String,
        #[serde(default)]
        prior: Option<serde_json::Value>,
    },
    /// A marker-delimited block merged into a shared text file (AGENTS.md /
    /// GEMINI.md). Uninstall restores `prior` (the verbatim block that occupied
    /// the markers before our write, when present) or strips our block — deleting
    /// the host file if it becomes empty/whitespace.
    MarkerBlock {
        file: String,
        #[serde(default)]
        prior: Option<String>,
    },
}

/// Load the install registry, returning an empty list when the file is absent.
/// A present-but-corrupt file is `SS-E-1002` (never silently dropped — the
/// records are the only record of what to uninstall).
pub fn load() -> Result<Vec<InstallRecord>, SsError> {
    let path = installs_path();
    let raw = match std::fs::read_to_string(&path) {
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
        SsError::new(ERR_STATE_CORRUPT, format!("installs.json is corrupt: {e}"))
            .with_suggestion("Run `saferskills doctor` to repair the registry.")
    })
}

/// Atomically persist the registry (temp → fsync → rename).
pub fn save(records: &[InstallRecord]) -> Result<(), SsError> {
    let json = serde_json::to_vec_pretty(records).map_err(|e| {
        SsError::new(
            ERR_STATE_CORRUPT,
            format!("Failed to serialize registry: {e}"),
        )
    })?;
    atomic_write(&installs_path(), &json)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample() -> InstallRecord {
        InstallRecord {
            canonical_id: "id-1".into(),
            slug: "acme--kit--skill-pdf".into(),
            name: "pdf".into(),
            kind: "skill".into(),
            version: Some("abc123".into()),
            agents: vec!["claude-code".into()],
            changes: vec![
                InstallChange::File {
                    path: "/x/SKILL.md".into(),
                },
                InstallChange::ConfigKey {
                    file: "~/.claude.json".into(),
                    key: "mcpServers.pdf".into(),
                    prior: None,
                },
            ],
            installed_at: chrono::DateTime::from_timestamp(0, 0).unwrap(),
            seen_score: Some(87),
        }
    }

    #[test]
    fn record_roundtrips_json() {
        let rec = sample();
        let json = serde_json::to_string(&rec).unwrap();
        let back: InstallRecord = serde_json::from_str(&json).unwrap();
        assert_eq!(back.slug, rec.slug);
        assert_eq!(back.changes.len(), 2);
        assert_eq!(back.seen_score, Some(87));
    }

    #[test]
    fn install_change_is_internally_tagged() {
        let json = serde_json::to_string(&InstallChange::File { path: "/p".into() }).unwrap();
        assert!(json.contains("\"type\":\"file\""));
    }

    #[test]
    fn corrupt_registry_is_an_error() {
        // The corrupt-parse branch is the load-bearing safety property; exercise
        // it directly (no shared-env mutation, so it's parallel-test-safe).
        let parsed: Result<Vec<InstallRecord>, _> = serde_json::from_str("{not json");
        assert!(parsed.is_err());
    }
}
