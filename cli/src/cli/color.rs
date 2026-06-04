//! Terminal color detection + colorblind-safe severity / tier rendering.
//!
//! Color precedence (D-05-11):
//! `--color=never` > `--no-color` / `NO_COLOR` > `--color=always` /
//! `CLICOLOR_FORCE` > `TERM=dumb` > `stdout().is_terminal()`.
//!
//! **Never color-alone** — every severity / tier carries a glyph + an
//! UPPERCASE label so the signal survives a monochrome or colorblind reader.

use std::io::IsTerminal;

use crate::api::dto::{Severity, Tier};

/// Tri-state color choice from the `--color` flag (mirrors clap's `ColorChoice`
/// without taking a dependency on it for this internal precedence logic).
#[derive(Debug, Clone, Copy, PartialEq, Eq, clap::ValueEnum)]
pub enum ColorChoice {
    /// Force color on.
    Always,
    /// Decide from environment + TTY (default).
    Auto,
    /// Force color off.
    Never,
}

/// Resolve whether ANSI color should be emitted.
pub fn is_color_enabled(explicit: Option<ColorChoice>, no_color_flag: bool) -> bool {
    match explicit {
        Some(ColorChoice::Never) => return false,
        Some(ColorChoice::Always) => return true,
        _ => {}
    }
    if no_color_flag {
        return false;
    }
    if std::env::var_os("NO_COLOR").is_some_and(|v| !v.is_empty()) {
        return false;
    }
    if std::env::var("CLICOLOR_FORCE").is_ok_and(|v| !v.is_empty() && v != "0") {
        return true;
    }
    if std::env::var("TERM").is_ok_and(|v| v == "dumb") {
        return false;
    }
    std::io::stdout().is_terminal()
}

// ---------------------------------------------------------------------------
// Primitive ANSI wrappers (raw escapes, 16-color safe)
// ---------------------------------------------------------------------------

fn paint(code: &str, text: &str, enabled: bool) -> String {
    if enabled {
        format!("\x1b[{code}m{text}\x1b[0m")
    } else {
        text.to_string()
    }
}

/// Green text when color is enabled.
pub fn green(text: &str, enabled: bool) -> String {
    paint("32", text, enabled)
}

/// Red text when color is enabled.
pub fn red(text: &str, enabled: bool) -> String {
    paint("31", text, enabled)
}

/// Dim (gray) text when color is enabled.
pub fn dim(text: &str, enabled: bool) -> String {
    paint("2", text, enabled)
}

/// Bold text when color is enabled.
pub fn bold(text: &str, enabled: bool) -> String {
    paint("1", text, enabled)
}

/// A success checkmark — green `✓` with color, plain `OK` without.
pub fn checkmark(enabled: bool) -> &'static str {
    if enabled {
        "\x1b[32m\u{2713}\x1b[0m"
    } else {
        "OK"
    }
}

/// An error cross — red `✗` with color, plain `ERR` without.
pub fn cross(enabled: bool) -> &'static str {
    if enabled {
        "\x1b[31m\u{2717}\x1b[0m"
    } else {
        "ERR"
    }
}

/// A warning glyph — yellow `⚠` with color, plain `!` without.
pub fn warn_glyph(enabled: bool) -> &'static str {
    if enabled {
        "\x1b[33m\u{26a0}\x1b[0m"
    } else {
        "!"
    }
}

/// An indented bullet — dim `·` with color, plain `-` without.
pub fn bullet(enabled: bool) -> &'static str {
    if enabled {
        "  \u{00b7}"
    } else {
        "  -"
    }
}

// ---------------------------------------------------------------------------
// Severity + tier badges (glyph + UPPERCASE label — never color-alone)
// ---------------------------------------------------------------------------

/// Render a finding-severity badge: glyph + UPPERCASE label. Color is purely an
/// enhancement — the glyph + label always carry the signal.
pub fn severity_badge(sev: Severity, enabled: bool) -> String {
    let (glyph, label, code) = match sev {
        Severity::Critical => ('\u{2717}', "CRITICAL", "31"), // ✗ red
        Severity::High => ('\u{25b2}', "HIGH", "31"),         // ▲ red
        Severity::Medium => ('\u{25c6}', "MEDIUM", "33"),     // ◆ yellow
        Severity::Low => ('\u{00b7}', "LOW", "33"),           // · yellow
        Severity::Info => ('\u{24d8}', "INFO", "2"),          // ⓘ dim
        Severity::Unknown => ('?', "UNKNOWN", "2"),
    };
    let body = format!("{glyph} {label}");
    paint(code, &body, enabled)
}

/// Render a score-tier dot: `●` + capitalized tier label.
pub fn tier_dot(tier: Tier, enabled: bool) -> String {
    let (label, code) = match tier {
        Tier::Green => ("Green", "32"),
        Tier::Yellow => ("Yellow", "33"),
        Tier::Orange => ("Orange", "33"),
        Tier::Red => ("Red", "31"),
        Tier::Unscoped => ("Unscoped", "2"),
        Tier::Unknown => ("Unknown", "2"),
    };
    let body = format!("\u{25cf} {label}");
    paint(code, &body, enabled)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn no_color_flag_overrides_tty() {
        assert!(!is_color_enabled(None, true));
    }

    #[test]
    fn explicit_always_beats_no_color_env() {
        // Even with the flag set, an explicit --color=always wins.
        assert!(is_color_enabled(Some(ColorChoice::Always), true));
    }

    #[test]
    fn explicit_never_forces_off() {
        assert!(!is_color_enabled(Some(ColorChoice::Never), false));
    }

    #[test]
    fn checkmark_plain_when_disabled() {
        assert_eq!(checkmark(false), "OK");
    }

    #[test]
    fn bullet_plain_when_disabled() {
        assert_eq!(bullet(false), "  -");
    }

    #[test]
    fn severity_badge_carries_label_without_color() {
        let s = severity_badge(Severity::Critical, false);
        assert!(s.contains("CRITICAL"));
        assert!(s.contains('\u{2717}'));
        assert!(!s.contains("\x1b["), "no ANSI when color is off");
    }

    #[test]
    fn severity_badge_adds_color_when_enabled() {
        let s = severity_badge(Severity::High, true);
        assert!(s.contains("HIGH"));
        assert!(s.contains("\x1b[31m"));
    }

    #[test]
    fn tier_dot_carries_label_without_color() {
        let s = tier_dot(Tier::Green, false);
        assert!(s.contains("Green"));
        assert!(s.contains('\u{25cf}'));
        assert!(!s.contains("\x1b["));
    }

    #[test]
    fn tier_dot_unscoped_renders() {
        assert!(tier_dot(Tier::Unscoped, false).contains("Unscoped"));
    }
}
