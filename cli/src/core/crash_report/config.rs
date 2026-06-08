//! Read the `[crashreport]` section of `~/.saferskills/config.toml`.
//!
//! Crash reporting does **not** have its own sidecar file — the toggle lives in
//! the main TOML config (a single boolean field sharing the same per-user
//! directory lifecycle as every other `config.toml` key).
//!
//! Default: **enabled** when the section is absent. Crash reports are
//! diagnostic, not behavioural usage analytics, so they default on (unlike the
//! opt-in PostHog `telemetry` key) — but they are still silenced by a universal
//! opt-out env or a build with no baked DSN (see [`super::consent`]).

use std::path::Path;

use serde::Deserialize;

/// On-disk shape of `[crashreport]`. The single field is optional so a missing
/// or partially-written section still parses.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(default)]
pub struct CrashreportSection {
    pub enabled: bool,
}

impl Default for CrashreportSection {
    fn default() -> Self {
        Self { enabled: true }
    }
}

/// Outer shape used for the partial TOML parse — we only care about the one
/// section and ignore every other top-level key.
#[derive(Debug, Default, Deserialize)]
struct PartialConfig {
    #[serde(default)]
    crashreport: Option<CrashreportSection>,
}

/// Parse the `[crashreport]` section from the given `config.toml` path.
///
/// Returns:
/// - `Ok(Some(section))` when the section is present.
/// - `Ok(None)` when the file does not exist OR the section is absent — the
///   consent layer treats both as "default on".
/// - `Err(...)` on I/O or TOML parse failure of the whole file (the consent
///   layer treats a parse error as "default on" too, so a corrupt file never
///   silently stops crash diagnostics).
pub fn read_section(path: &Path) -> Result<Option<CrashreportSection>, ReadError> {
    let raw = match std::fs::read_to_string(path) {
        Ok(s) => s,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(ReadError::Io(e.to_string())),
    };
    let parsed: PartialConfig =
        toml::from_str(&raw).map_err(|e| ReadError::Parse(e.to_string()))?;
    Ok(parsed.crashreport)
}

#[derive(Debug)]
pub enum ReadError {
    Io(String),
    Parse(String),
}

impl std::fmt::Display for ReadError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ReadError::Io(s) => write!(f, "config.toml read error: {s}"),
            ReadError::Parse(s) => write!(f, "config.toml parse error: {s}"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn read_section_missing_file_returns_none() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("config.toml");
        assert!(read_section(&path).unwrap().is_none());
    }

    #[test]
    fn read_section_absent_returns_none() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("config.toml");
        std::fs::write(&path, "api_url = \"https://x.test\"\n").unwrap();
        assert!(read_section(&path).unwrap().is_none());
    }

    #[test]
    fn read_section_enabled_true() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("config.toml");
        std::fs::write(&path, "[crashreport]\nenabled = true\n").unwrap();
        assert_eq!(
            read_section(&path).unwrap(),
            Some(CrashreportSection { enabled: true })
        );
    }

    #[test]
    fn read_section_enabled_false() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("config.toml");
        std::fs::write(&path, "[crashreport]\nenabled = false\n").unwrap();
        assert_eq!(
            read_section(&path).unwrap(),
            Some(CrashreportSection { enabled: false })
        );
    }

    #[test]
    fn read_section_empty_section_defaults_enabled() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("config.toml");
        std::fs::write(&path, "[crashreport]\n").unwrap();
        assert_eq!(
            read_section(&path).unwrap(),
            Some(CrashreportSection { enabled: true })
        );
    }
}
