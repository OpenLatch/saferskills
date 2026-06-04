//! Structured, user-facing error type for the `saferskills` CLI.
//!
//! Mirrors `openlatch-client`'s `OlError` with a SaferSkills `SS-E-XXXX` code
//! registry (D-05-12). Every error carries a stable code, a human-readable
//! message, and optional suggestion + docs URL. The `Display` impl renders the
//! multi-line human form; `--json` callers serialize `{"error": {…}}` via
//! [`crate::cli::output::OutputConfig::print_error`]. `miette::Diagnostic` is
//! implemented so `--verbose` can render a fancy boundary diagnostic.
//!
//! ## Code registry (numeric ranges by subsystem; codes are NEVER reused)
//!
//! ```text
//! SS-E-1000s  config / local state
//! SS-E-1100s  network / API
//! SS-E-1200s  resolution / not-found
//! SS-E-1300s  install gating          (Phase B)
//! SS-E-1400s  agent detection         (Phase B)
//! SS-E-1500s  config writers          (Phase B)
//! SS-E-1600s  scan / upload           (Phase C)
//! SS-E-9999   internal bug (pre-filled GitHub issue URL)
//! ```
//!
//! ## Exit codes (D-05-11)
//!
//! `0` ok · `1` generic / findings-block · `2` usage (clap) · `3` not-found ·
//! `4` permission · `5` conflict · `6` network / rate-limit · `130` SIGINT.

use std::fmt;

/// A structured, user-facing error with an `SS-E-XXXX` code.
#[derive(Debug, Clone)]
pub struct SsError {
    /// The stable `SS-E-XXXX` error code.
    pub code: &'static str,
    /// Human-readable, actionable description.
    pub message: String,
    /// Optional fix suggestion.
    pub suggestion: Option<String>,
    /// Optional docs link for this error.
    pub docs_url: Option<String>,
    /// Explicit process exit-code override. When `None`, the exit code is
    /// derived from the code range (see [`SsError::exit_code`]).
    exit: Option<i32>,
}

impl SsError {
    /// Create a new error with the given code and message.
    pub fn new(code: &'static str, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
            suggestion: None,
            docs_url: None,
            exit: None,
        }
    }

    /// Attach a fix suggestion.
    pub fn with_suggestion(mut self, s: impl Into<String>) -> Self {
        self.suggestion = Some(s.into());
        self
    }

    /// Attach a docs URL.
    pub fn with_docs(mut self, url: impl Into<String>) -> Self {
        self.docs_url = Some(url.into());
        self
    }

    /// Override the process exit code (for permission `4` / conflict `5`
    /// classes that aren't a whole numeric range).
    pub fn with_exit_code(mut self, code: i32) -> Self {
        self.exit = Some(code);
        self
    }

    /// Build a "bug report" error pre-filled with a GitHub issue URL.
    pub fn bug_report(message: impl Into<String>) -> Self {
        let msg = message.into();
        let url = format!(
            "https://github.com/OpenLatch/saferskills/issues/new?title={}&body={}",
            percent_encode(&msg),
            percent_encode("Version: [auto]\nOS: [auto]\n\nDescription:\n"),
        );
        Self {
            code: ERR_BUG,
            message: msg,
            suggestion: Some("This is a bug. Please report it.".into()),
            docs_url: Some(url),
            exit: Some(1),
        }
    }

    /// Map the error to a process exit code (D-05-11).
    ///
    /// An explicit override (set via [`SsError::with_exit_code`]) wins;
    /// otherwise the code is derived from the numeric range: `1100s` →
    /// `6` (network/rate-limit), `1200s` → `3` (not-found), else `1`.
    pub fn exit_code(&self) -> i32 {
        if let Some(c) = self.exit {
            return c;
        }
        match self.numeric() {
            Some(n) if (1100..1200).contains(&n) => 6,
            Some(n) if (1200..1300).contains(&n) => 3,
            _ => 1,
        }
    }

    /// Parse the numeric portion of the `SS-E-XXXX` code.
    fn numeric(&self) -> Option<u32> {
        self.code.strip_prefix("SS-E-").and_then(|s| s.parse().ok())
    }
}

impl fmt::Display for SsError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{} ({})", self.message, self.code)?;
        if self.suggestion.is_some() || self.docs_url.is_some() {
            writeln!(f)?;
            writeln!(f)?;
            if let Some(ref s) = self.suggestion {
                writeln!(f, "  Suggestion: {s}")?;
            }
            if let Some(ref url) = self.docs_url {
                write!(f, "  Docs: {url}")?;
            }
        }
        Ok(())
    }
}

impl std::error::Error for SsError {}

impl miette::Diagnostic for SsError {
    fn code<'a>(&'a self) -> Option<Box<dyn fmt::Display + 'a>> {
        Some(Box::new(self.code))
    }

    fn help<'a>(&'a self) -> Option<Box<dyn fmt::Display + 'a>> {
        self.suggestion
            .as_ref()
            .map(|s| Box::new(s.clone()) as Box<dyn fmt::Display>)
    }

    fn url<'a>(&'a self) -> Option<Box<dyn fmt::Display + 'a>> {
        self.docs_url
            .as_ref()
            .map(|u| Box::new(u.clone()) as Box<dyn fmt::Display>)
    }
}

/// Minimal percent-encoding for the `bug_report` GitHub query string. Encodes
/// only the characters that break URL structure — avoids a `url`/`percent-
/// encoding` dependency for a single call site.
fn percent_encode(input: &str) -> String {
    let mut out = String::with_capacity(input.len());
    for c in input.chars() {
        match c {
            ' ' => out.push_str("%20"),
            '\n' => out.push_str("%0A"),
            '\r' => out.push_str("%0D"),
            '&' => out.push_str("%26"),
            '=' => out.push_str("%3D"),
            '#' => out.push_str("%23"),
            other => out.push(other),
        }
    }
    out
}

// ---------------------------------------------------------------------------
// SS-E-1000s — config / local state
// ---------------------------------------------------------------------------

/// `config.toml` contains an invalid value.
pub const ERR_INVALID_CONFIG: &str = "SS-E-1000";
/// Failed to write `config.toml` (permission or I/O error).
pub const ERR_CONFIG_WRITE_FAILED: &str = "SS-E-1001";
/// `installs.json` exists but cannot be parsed (corrupt registry).
pub const ERR_STATE_CORRUPT: &str = "SS-E-1002";
/// Atomic write of a local-state file failed.
pub const ERR_STATE_WRITE_FAILED: &str = "SS-E-1003";
/// A filesystem operation was denied (permission). Exit code `4`.
pub const ERR_PERMISSION: &str = "SS-E-1004";
/// A command exists in the grammar but is not wired up in this build yet
/// (Phase B/C stub). Kept in the config/state range as a generic CLI-internal
/// signal — it is not a user input error.
pub const ERR_NOT_IMPLEMENTED: &str = "SS-E-1090";

// ---------------------------------------------------------------------------
// SS-E-1100s — network / API
// ---------------------------------------------------------------------------

/// Could not reach the SaferSkills API (DNS / connect / timeout). Exit `6`.
pub const ERR_NETWORK: &str = "SS-E-1100";
/// The API returned a non-success HTTP status. Exit `6`.
pub const ERR_API_STATUS: &str = "SS-E-1101";
/// The API returned 429 (rate limited). Exit `6` (should not occur on reads).
pub const ERR_RATE_LIMITED: &str = "SS-E-1102";
/// The API response body failed to deserialize into the expected DTO. Exit `6`.
pub const ERR_API_DECODE: &str = "SS-E-1103";

// ---------------------------------------------------------------------------
// SS-E-1200s — resolution / not-found
// ---------------------------------------------------------------------------

/// The typed name did not resolve to any catalog item. Exit `3`.
pub const ERR_ITEM_NOT_FOUND: &str = "SS-E-1200";

// ---------------------------------------------------------------------------
// SS-E-1300s — install gating (Phase B)
// ---------------------------------------------------------------------------

/// An already-installed item collided with the registry and no resolution flag
/// (`--update` / `--reinstall` / `--to`) was given. Exit `5` (conflict).
pub const ERR_CONFLICT: &str = "SS-E-1300";
/// The user declined a severity gate (answered no / mismatched the type-the-name
/// confirm). Exit `1`.
pub const ERR_GATE_CANCELLED: &str = "SS-E-1301";
/// A required choice could not be made non-interactively (e.g. `--to`/`--all`
/// needed, or a gate hit without `--yes`/`--force`). Exit `2` (usage).
pub const ERR_NEEDS_FLAG: &str = "SS-E-1302";

// ---------------------------------------------------------------------------
// SS-E-1400s — agent detection (Phase B)
// ---------------------------------------------------------------------------

/// No supported agents were detected on the machine (CLI-9). Exit `1`.
pub const ERR_NO_AGENTS: &str = "SS-E-1400";
/// A `--to <agent>` token did not name a known agent. Exit `2` (usage).
pub const ERR_UNKNOWN_AGENT: &str = "SS-E-1401";

// ---------------------------------------------------------------------------
// SS-E-1500s — config writers (Phase B)
// ---------------------------------------------------------------------------

/// A config write failed mid-flight; partial edits were rolled back (D-05-24).
/// Exit `1`.
pub const ERR_WRITE_ROLLBACK: &str = "SS-E-1500";
/// The selected agent cannot install this capability (kind/scope unsupported).
/// Exit `1`.
pub const ERR_WRITER_UNSUPPORTED: &str = "SS-E-1501";

// ---------------------------------------------------------------------------
// SS-E-1600s — scan / upload (Phase C)
// ---------------------------------------------------------------------------

/// A scan submission was rejected by the API gate (PoW / rate-limit / captcha).
/// Exit `1`.
pub const ERR_SCAN_SUBMIT: &str = "SS-E-1600";
/// The submitted scan did not complete before the client timeout. Exit `1`.
pub const ERR_SCAN_TIMEOUT: &str = "SS-E-1601";
/// The Proof-of-Work challenge could not be obtained or solved. Exit `1`.
pub const ERR_POW_FAILED: &str = "SS-E-1602";
/// The scan target is missing / empty / not a readable path or GitHub URL.
/// Exit `1`.
pub const ERR_SCAN_TARGET: &str = "SS-E-1603";

// ---------------------------------------------------------------------------
// SS-E-9999 — internal bug
// ---------------------------------------------------------------------------

/// Code assigned to all internal/unexpected errors routed through `bug_report`.
pub const ERR_BUG: &str = "SS-E-9999";

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn display_full_format() {
        let err = SsError::new(ERR_ITEM_NOT_FOUND, "Item not found in catalog: \"x\"")
            .with_suggestion("Try: saferskills scan <github-url>")
            .with_docs("https://saferskills.ai/docs/errors/SS-E-1200");
        let out = format!("{err}");
        assert!(out.starts_with("Item not found in catalog: \"x\" (SS-E-1200)"));
        assert!(out.contains("Suggestion: Try: saferskills scan"));
        assert!(out.contains("Docs: https://saferskills.ai"));
    }

    #[test]
    fn display_no_optional_fields() {
        let err = SsError::new(ERR_INVALID_CONFIG, "bad value");
        assert_eq!(format!("{err}"), "bad value (SS-E-1000)");
    }

    #[test]
    fn exit_code_derives_from_range() {
        assert_eq!(SsError::new(ERR_NETWORK, "x").exit_code(), 6);
        assert_eq!(SsError::new(ERR_RATE_LIMITED, "x").exit_code(), 6);
        assert_eq!(SsError::new(ERR_ITEM_NOT_FOUND, "x").exit_code(), 3);
        assert_eq!(SsError::new(ERR_INVALID_CONFIG, "x").exit_code(), 1);
    }

    #[test]
    fn exit_code_override_wins() {
        let err = SsError::new(ERR_PERMISSION, "denied").with_exit_code(4);
        assert_eq!(err.exit_code(), 4);
    }

    #[test]
    fn bug_report_sets_code_and_url() {
        let err = SsError::bug_report("unexpected");
        assert_eq!(err.code, ERR_BUG);
        assert!(err
            .docs_url
            .unwrap()
            .contains("OpenLatch/saferskills/issues/new"));
    }

    #[test]
    fn percent_encode_escapes_structure() {
        assert_eq!(percent_encode("a b"), "a%20b");
        assert_eq!(percent_encode("x\ny"), "x%0Ay");
    }

    #[test]
    fn implements_std_error() {
        let err = SsError::new(ERR_BUG, "x");
        let _boxed: Box<dyn std::error::Error> = Box::new(err);
    }
}
