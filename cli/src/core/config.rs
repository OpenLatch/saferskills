//! Local state + configuration under `~/.saferskills/` (D-05-10, D-05-28).
//!
//! Files:
//! - `config.toml` — commented template; active keys `api_url`,
//!   `gate_threshold`, `telemetry`.
//! - `installs.json` — the install registry (see [`crate::core::registry`]).
//! - `bin/` — postinstall-fallback binary cache.
//! - `cache/` — rules-content cache.
//!
//! Precedence: CLI flags > `SAFERSKILLS_*` env > `config.toml` > defaults.
//! All writes are atomic: a temp file in the SAME directory → fsync → rename.

use std::fs;
use std::io::Write as _;
use std::path::PathBuf;

use serde::Deserialize;

use crate::core::error::{
    SsError, ERR_CONFIG_WRITE_FAILED, ERR_INVALID_CONFIG, ERR_STATE_WRITE_FAILED,
};

/// Default API origin (reads go same-origin through the webapp `/api/*` proxy).
pub const DEFAULT_API_BASE: &str = "https://saferskills.ai";

/// Resolve the SaferSkills home directory: `SAFERSKILLS_DIR` env override, else
/// `~/.saferskills` (matches the PRD on every OS; `%USERPROFILE%` resolves the
/// home on Windows via `dirs`).
pub fn saferskills_dir() -> PathBuf {
    if let Ok(dir) = std::env::var("SAFERSKILLS_DIR") {
        if !dir.is_empty() {
            return PathBuf::from(dir);
        }
    }
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".saferskills")
}

/// `~/.saferskills/config.toml`.
pub fn config_path() -> PathBuf {
    saferskills_dir().join("config.toml")
}

/// `~/.saferskills/installs.json`.
pub fn installs_path() -> PathBuf {
    saferskills_dir().join("installs.json")
}

/// `~/.saferskills/cache/`.
pub fn cache_dir() -> PathBuf {
    saferskills_dir().join("cache")
}

/// `~/.saferskills/bin/`.
pub fn bin_dir() -> PathBuf {
    saferskills_dir().join("bin")
}

/// Ensure the SaferSkills home directory exists.
pub fn ensure_dir() -> Result<(), SsError> {
    let dir = saferskills_dir();
    fs::create_dir_all(&dir).map_err(|e| {
        SsError::new(
            ERR_STATE_WRITE_FAILED,
            format!("Failed to create {}: {e}", dir.display()),
        )
        .with_exit_code(if e.kind() == std::io::ErrorKind::PermissionDenied {
            4
        } else {
            1
        })
    })
}

/// On-disk `config.toml` shape. All keys optional — absence means "use the
/// default" (D-05-10). Unknown keys are ignored.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct Config {
    /// Override the API origin.
    pub api_url: Option<String>,
    /// Lowest finding severity that prompts. Default `medium`.
    pub gate_threshold: Option<String>,
    /// Usage analytics (PostHog) consent. `None` = not yet chosen — the CLI
    /// prompts once on the first interactive launch and stores the answer here.
    /// (Install reporting is unconditional and has no config key.)
    pub telemetry: Option<bool>,
    /// Whether the one-time first-launch security audit has been offered/run.
    /// `Some(true)` short-circuits the prompt so it never re-asks (D-05-26).
    pub audited: Option<bool>,
}

impl Config {
    /// Load `config.toml`, returning defaults when the file is absent. A
    /// present-but-malformed file is a hard `SS-E-1000` (the user asked us to
    /// read it; silently ignoring a typo would mask their intent).
    pub fn load() -> Result<Self, SsError> {
        let path = config_path();
        let raw = match fs::read_to_string(&path) {
            Ok(s) => s,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(Self::default()),
            Err(e) => {
                return Err(SsError::new(
                    ERR_INVALID_CONFIG,
                    format!("Failed to read {}: {e}", path.display()),
                ))
            }
        };
        toml::from_str(&raw).map_err(|e| {
            SsError::new(ERR_INVALID_CONFIG, format!("Invalid config.toml: {e}"))
                .with_suggestion("Fix the syntax, or delete the file to restore defaults.")
        })
    }

    /// Resolve the API base URL: `SAFERSKILLS_API_URL` env > `api_url` config >
    /// [`DEFAULT_API_BASE`]. A `cli_override` (future `--api-url`) wins outright.
    pub fn api_base(&self, cli_override: Option<&str>) -> String {
        if let Some(v) = cli_override {
            return v.trim_end_matches('/').to_string();
        }
        if let Ok(v) = std::env::var("SAFERSKILLS_API_URL") {
            if !v.is_empty() {
                return v.trim_end_matches('/').to_string();
            }
        }
        self.api_url
            .as_deref()
            .filter(|v| !v.is_empty())
            .unwrap_or(DEFAULT_API_BASE)
            .trim_end_matches('/')
            .to_string()
    }
}

/// The commented `config.toml` template written on first run.
pub fn default_config_toml() -> &'static str {
    "# SaferSkills CLI configuration (~/.saferskills/config.toml)\n\
     # Every key is optional; uncomment to override the default.\n\
     \n\
     # API origin the CLI reads from. Default: https://saferskills.ai\n\
     # api_url = \"https://saferskills.ai\"\n\
     \n\
     # Lowest finding severity that prompts before install.\n\
     # One of: info | low | medium | high | critical. Default: medium\n\
     # gate_threshold = \"medium\"\n\
     \n\
     # Anonymous usage analytics (PostHog). Asked once on first run; stored here.\n\
     # Set false to opt out — also disabled by SAFERSKILLS_NO_TELEMETRY /\n\
     # DO_NOT_TRACK / CI, or forced on with SAFERSKILLS_TELEMETRY=1.\n\
     # (Anonymous install counts are reported automatically; the same opt-out\n\
     # envs above suppress them too.)\n\
     # telemetry = false\n\
     \n\
     # Set true once the one-time first-launch security audit has been offered.\n\
     # Managed by the CLI; you should not need to edit this.\n\
     # audited = false\n"
}

/// Persist the usage-analytics `telemetry` consent to `config.toml`, preserving
/// the commented template + any existing keys (toml_edit). Best-effort: the
/// caller treats a write failure as non-fatal (the choice still applies this run).
pub fn set_telemetry(value: bool) -> Result<(), SsError> {
    let path = config_path();
    let base = fs::read_to_string(&path).unwrap_or_else(|_| default_config_toml().to_string());
    let mut doc = base.parse::<toml_edit::DocumentMut>().unwrap_or_default();
    doc["telemetry"] = toml_edit::value(value);
    ensure_dir()?;
    atomic_write(&path, doc.to_string().as_bytes())
}

/// Persist the one-time first-launch audit flag to `config.toml`, preserving the
/// commented template + any existing keys (toml_edit). Best-effort — the caller
/// treats a write failure as non-fatal (the audit is fail-open).
pub fn set_audited(value: bool) -> Result<(), SsError> {
    let path = config_path();
    let base = fs::read_to_string(&path).unwrap_or_else(|_| default_config_toml().to_string());
    let mut doc = base.parse::<toml_edit::DocumentMut>().unwrap_or_default();
    doc["audited"] = toml_edit::value(value);
    ensure_dir()?;
    atomic_write(&path, doc.to_string().as_bytes())
}

/// Write the default `config.toml` if it does not already exist.
pub fn write_default_config_if_missing() -> Result<(), SsError> {
    let path = config_path();
    if path.exists() {
        return Ok(());
    }
    ensure_dir()?;
    atomic_write(&path, default_config_toml().as_bytes())
        .map_err(|e| SsError::new(ERR_CONFIG_WRITE_FAILED, e.message))
}

/// Atomically write `bytes` to `path`: a `NamedTempFile` in the SAME directory
/// → flush + fsync → atomic rename. The same-directory temp guarantees the
/// rename is atomic (no cross-device copy).
pub fn atomic_write(path: &std::path::Path, bytes: &[u8]) -> Result<(), SsError> {
    let parent = path.parent().unwrap_or_else(|| std::path::Path::new("."));
    fs::create_dir_all(parent).map_err(|e| write_err(path, e))?;

    let mut tmp = tempfile::NamedTempFile::new_in(parent).map_err(|e| write_err(path, e))?;
    tmp.write_all(bytes).map_err(|e| write_err(path, e))?;
    tmp.as_file().sync_all().map_err(|e| write_err(path, e))?;
    tmp.persist(path).map_err(|e| write_err(path, e.error))?;
    Ok(())
}

fn write_err(path: &std::path::Path, e: std::io::Error) -> SsError {
    let exit = if e.kind() == std::io::ErrorKind::PermissionDenied {
        4
    } else {
        1
    };
    SsError::new(
        ERR_STATE_WRITE_FAILED,
        format!("Failed to write {}: {e}", path.display()),
    )
    .with_exit_code(exit)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn saferskills_dir_honors_env_override() {
        // SAFETY: single-threaded test; we set then read the override.
        std::env::set_var("SAFERSKILLS_DIR", "/tmp/ss-test-dir");
        assert_eq!(saferskills_dir(), PathBuf::from("/tmp/ss-test-dir"));
        std::env::remove_var("SAFERSKILLS_DIR");
    }

    #[test]
    fn config_defaults_resolve_api_base() {
        let cfg = Config::default();
        assert_eq!(cfg.api_base(None), DEFAULT_API_BASE);
        assert_eq!(cfg.api_base(Some("https://x.test/")), "https://x.test");
    }

    #[test]
    fn parse_config_toml() {
        let cfg: Config =
            toml::from_str("api_url = \"https://staging.test\"\ngate_threshold = \"high\"\n")
                .unwrap();
        assert_eq!(cfg.api_url.as_deref(), Some("https://staging.test"));
        assert_eq!(cfg.gate_threshold.as_deref(), Some("high"));
        assert!(cfg.telemetry.is_none()); // unset → not yet chosen (prompted on first run)
    }

    #[test]
    fn atomic_write_roundtrip() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("nested").join("f.txt");
        atomic_write(&path, b"hello").unwrap();
        assert_eq!(fs::read_to_string(&path).unwrap(), "hello");
        // Idempotent overwrite.
        atomic_write(&path, b"world").unwrap();
        assert_eq!(fs::read_to_string(&path).unwrap(), "world");
    }

    #[test]
    fn default_template_is_all_comments() {
        for line in default_config_toml()
            .lines()
            .filter(|l| !l.trim().is_empty())
        {
            assert!(
                line.trim_start().starts_with('#'),
                "active key in template: {line}"
            );
        }
    }
}
