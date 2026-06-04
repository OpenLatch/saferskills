//! The SaferSkills CLI banner.
//!
//! Two lines, both to **stderr**, suppressed in Json / quiet:
//!
//! ```text
//! ▄▄▄ SaferSkills ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
//!     An OpenLatch project
//! ```
//!
//! Brand rules (`.claude/rules/design-system.md`): the wordmark is ALWAYS
//! camelCase `SaferSkills`; the footer line is EXACTLY `An OpenLatch project`
//! and is the ONLY OpenLatch string permitted anywhere in CLI output
//! (anti-recommendation — no other OpenLatch reference in any banner/help/error).

use crate::cli::output::{OutputConfig, OutputFormat};

/// Brand label rendered between the leading and trailing fill (with padding).
const LABEL: &str = " SaferSkills ";
/// The single permitted OpenLatch attribution line.
const FOOTER: &str = "    An OpenLatch project";
/// Leading fill glyph count.
const LEAD: usize = 3;
/// Fallback width when `COLUMNS` is unset (non-TTY / redirected stderr).
const FALLBACK_WIDTH: usize = 44;
/// Upper bound — past this the rule is visual noise rather than a frame.
const MAX_WIDTH: usize = 120;

/// Detect terminal width with zero dependencies: read `COLUMNS`, else fall
/// back. `indicatif` already does TTY sizing for spinners; the banner only
/// needs a reasonable frame width.
fn detect_width() -> usize {
    std::env::var("COLUMNS")
        .ok()
        .and_then(|v| v.trim().parse::<usize>().ok())
        .filter(|w| *w > 0)
        .unwrap_or(FALLBACK_WIDTH)
}

/// Build the brand rule sized to the terminal: `▄▄▄ SaferSkills ▄…▄` (color) or
/// `=== SaferSkills ===…=` (plain).
fn build_rule(color: bool) -> String {
    let min_width = LEAD + LABEL.chars().count() + 1;
    let width = detect_width().clamp(min_width, MAX_WIDTH);

    let fill = if color { '\u{2584}' } else { '=' };
    let lead: String = std::iter::repeat_n(fill, LEAD).collect();
    let tail_len = width - LEAD - LABEL.chars().count();
    let tail: String = std::iter::repeat_n(fill, tail_len).collect();

    if color {
        format!("\x1b[36m{lead}{LABEL}{tail}\x1b[0m")
    } else {
        format!("{lead}{LABEL}{tail}")
    }
}

/// Print the brand rule only (used as a help preamble on the no-subcommand
/// path). Suppressed in Json / quiet; written to stderr.
pub fn print_full_banner(output: &OutputConfig) {
    if output.format == OutputFormat::Json || output.quiet {
        return;
    }
    eprintln!("{}", build_rule(output.color));
}

/// Print the two-line banner (rule + the OpenLatch attribution footer).
/// Suppressed in Json / quiet; written to stderr.
pub fn print(output: &OutputConfig) {
    if output.format == OutputFormat::Json || output.quiet {
        return;
    }
    eprintln!("{}", build_rule(output.color));
    eprintln!("{FOOTER}");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rule_contains_camelcase_wordmark() {
        assert!(build_rule(false).contains("SaferSkills"));
        assert!(build_rule(true).contains("SaferSkills"));
    }

    #[test]
    fn footer_is_the_only_openlatch_string() {
        assert_eq!(FOOTER.trim(), "An OpenLatch project");
    }

    #[test]
    fn plain_rule_has_no_ansi() {
        assert!(!build_rule(false).contains("\x1b["));
    }

    #[test]
    fn width_clamped_to_max() {
        // Even a huge COLUMNS can't exceed MAX_WIDTH worth of glyphs.
        let rule = build_rule(false);
        assert!(rule.chars().count() <= MAX_WIDTH + 8);
    }
}
