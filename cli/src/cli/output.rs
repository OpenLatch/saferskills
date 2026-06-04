//! Output authority for the `saferskills` CLI (D-05-11).
//!
//! [`OutputConfig`] is the single source of truth for how a command emits
//! output. The discipline is absolute:
//!
//! - **stdout** = machine data only (`--json` payloads via [`OutputConfig::print_json`]).
//! - **stderr** = everything human (steps `✓`, substeps `·`, warnings `⚠`,
//!   info, errors, banner, spinners).
//!
//! `--json` (Json format) and `--quiet` suppress all human output; spinners are
//! `None` in those modes and on non-TTY.

use crate::cli::color;
use crate::core::error::SsError;

/// Output format selection.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, clap::ValueEnum)]
pub enum OutputFormat {
    /// Human-readable, colorized when allowed (default).
    #[default]
    Human,
    /// Pure JSON — one object per logical result, to stdout.
    Json,
}

/// Resolved output configuration for one CLI invocation. Built once at startup
/// by [`crate::cli::build_output_config`] and threaded through commands.
#[derive(Debug, Clone)]
pub struct OutputConfig {
    /// Human vs JSON.
    pub format: OutputFormat,
    /// Verbose output (full finding lists, cause chains).
    pub verbose: bool,
    /// Quiet — suppress info/step output.
    pub quiet: bool,
    /// Whether ANSI color is allowed.
    pub color: bool,
}

impl OutputConfig {
    /// True when human output is suppressed (Json or quiet).
    fn human_suppressed(&self) -> bool {
        self.format == OutputFormat::Json || self.quiet
    }

    /// Print a completed-step line (`✓ …`) to stderr. Silent in Json/quiet.
    pub fn print_step(&self, message: &str) {
        if self.human_suppressed() {
            return;
        }
        eprintln!("{} {message}", color::checkmark(self.color));
    }

    /// Print an indented substep (`· …`) to stderr. Silent in Json/quiet.
    pub fn print_substep(&self, message: &str) {
        if self.human_suppressed() {
            return;
        }
        eprintln!("{} {message}", color::bullet(self.color));
    }

    /// Print a warning line (`⚠ …`) to stderr. Silent in Json/quiet.
    pub fn print_warn(&self, message: &str) {
        if self.human_suppressed() {
            return;
        }
        eprintln!("{} {message}", color::warn_glyph(self.color));
    }

    /// Print an informational line to stderr. Silent in Json/quiet.
    pub fn print_info(&self, message: &str) {
        if self.human_suppressed() {
            return;
        }
        eprintln!("{message}");
    }

    /// Print a structured [`SsError`].
    ///
    /// Human mode → multi-line `✗ Error: …` on stderr. Json mode →
    /// `{"error": {…}}` on stderr (stdout stays reserved for the data payload,
    /// which a failed command never produced).
    pub fn print_error(&self, error: &SsError) {
        match self.format {
            OutputFormat::Human => {
                let prefix = color::red("Error:", self.color);
                eprintln!(
                    "{} {prefix} {} ({})",
                    color::cross(self.color),
                    error.message,
                    error.code
                );
                if error.suggestion.is_some() || error.docs_url.is_some() {
                    eprintln!();
                    if let Some(ref s) = error.suggestion {
                        eprintln!("  Suggestion: {s}");
                    }
                    if let Some(ref url) = error.docs_url {
                        eprintln!("  Docs: {url}");
                    }
                }
            }
            OutputFormat::Json => {
                let json = serde_json::json!({
                    "error": {
                        "code": error.code,
                        "message": error.message,
                        "suggestion": error.suggestion,
                        "docs_url": error.docs_url,
                    }
                });
                eprintln!(
                    "{}",
                    serde_json::to_string_pretty(&json).unwrap_or_default()
                );
            }
        }
    }

    /// Serialize a value as pretty JSON to **stdout**. Never panics — a
    /// serialization failure is reported to stderr instead.
    pub fn print_json<T: serde::Serialize>(&self, value: &T) {
        match serde_json::to_string_pretty(value) {
            Ok(s) => println!("{s}"),
            Err(e) => eprintln!("Error: failed to serialize JSON output: {e}"),
        }
    }

    /// True when `--json` is active.
    pub fn is_json(&self) -> bool {
        self.format == OutputFormat::Json
    }

    /// True when `--quiet` is active.
    pub fn is_quiet(&self) -> bool {
        self.quiet
    }

    /// Create an `indicatif` spinner drawing to **stderr**. Returns `None` in
    /// Json/quiet mode and on non-TTY (the spinner hides itself there anyway).
    pub fn create_spinner(&self, message: &str) -> Option<indicatif::ProgressBar> {
        if self.human_suppressed() {
            return None;
        }
        let pb = indicatif::ProgressBar::new_spinner();
        pb.set_draw_target(indicatif::ProgressDrawTarget::stderr());
        pb.set_message(message.to_string());
        pb.enable_steady_tick(std::time::Duration::from_millis(80));
        Some(pb)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::error::ERR_ITEM_NOT_FOUND;

    fn cfg(format: OutputFormat, quiet: bool) -> OutputConfig {
        OutputConfig {
            format,
            verbose: false,
            quiet,
            color: false,
        }
    }

    #[test]
    fn is_quiet_reflects_flag() {
        assert!(cfg(OutputFormat::Human, true).is_quiet());
        assert!(!cfg(OutputFormat::Human, false).is_quiet());
    }

    #[test]
    fn spinner_none_in_json_mode() {
        assert!(cfg(OutputFormat::Json, false).create_spinner("x").is_none());
    }

    #[test]
    fn spinner_none_in_quiet_mode() {
        assert!(cfg(OutputFormat::Human, true).create_spinner("x").is_none());
    }

    #[test]
    fn print_json_does_not_panic() {
        let value = serde_json::json!({"status": "ok"});
        cfg(OutputFormat::Json, false).print_json(&value);
    }

    #[test]
    fn print_error_no_panic_both_modes() {
        let err = SsError::new(ERR_ITEM_NOT_FOUND, "nope").with_suggestion("try x");
        cfg(OutputFormat::Human, false).print_error(&err);
        cfg(OutputFormat::Json, false).print_error(&err);
    }

    #[test]
    fn human_output_silent_in_json_or_quiet() {
        // No assertion on captured output (stderr capture is process-level) —
        // these must simply branch early without panicking.
        cfg(OutputFormat::Json, false).print_step("x");
        cfg(OutputFormat::Human, true).print_substep("x");
        cfg(OutputFormat::Json, false).print_warn("x");
    }
}
