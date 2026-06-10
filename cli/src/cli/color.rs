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

/// The 5 scoring axes, in fixed display order, with their report labels. Shared
/// by the `capability` run report and the `install` digest.
pub const AXES: [(&str, &str); 5] = [
    ("security", "Security"),
    ("supply_chain", "Supply chain"),
    ("maintenance", "Maintenance"),
    ("transparency", "Transparency"),
    ("community", "Community"),
];

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

// ---------------------------------------------------------------------------
// Score gauges + tier glyphs + OSC 8 links (the audit-report vocabulary)
// ---------------------------------------------------------------------------

/// The ANSI code for a 0–100 score band, mirroring the webapp `--score-*`
/// thresholds: ≥80 green, ≥60 yellow, ≥40 orange (256-color), else red.
pub fn score_color_code(score: u8) -> &'static str {
    match score {
        s if s >= 80 => "32",       // green
        s if s >= 60 => "33",       // yellow
        s if s >= 40 => "38;5;208", // orange (256-color)
        _ => "31",                  // red
    }
}

/// A horizontal bar gauge — `█`×round(score/100·width) filled + `░`×rest,
/// colored by the score band. With color off it degrades to a plain
/// `██████░░░░` that pipes cleanly.
pub fn bar_gauge(score: u8, width: usize, enabled: bool) -> String {
    let score = score.min(100);
    let filled = ((score as usize * width) + 50) / 100; // round to nearest
    let filled = filled.min(width);
    let bar: String = "\u{2588}".repeat(filled) + &"\u{2591}".repeat(width - filled);
    paint(score_color_code(score), &bar, enabled)
}

/// A distinct glyph per tier so tiers differ without color — Green `●`,
/// Yellow `◐`, Orange `◑`, Red `✗`, Unscoped/Unknown `○`.
pub fn tier_glyph(tier: Tier) -> char {
    match tier {
        Tier::Green => '\u{25cf}',                    // ●
        Tier::Yellow => '\u{25d0}',                   // ◐
        Tier::Orange => '\u{25d1}',                   // ◑
        Tier::Red => '\u{2717}',                      // ✗
        Tier::Unscoped | Tier::Unknown => '\u{25cb}', // ○
    }
}

/// The ANSI code for a tier badge (matches `tier_dot`).
fn tier_code(tier: Tier) -> &'static str {
    match tier {
        Tier::Green => "32",
        Tier::Yellow | Tier::Orange => "33",
        Tier::Red => "31",
        Tier::Unscoped | Tier::Unknown => "2",
    }
}

/// A `tier_glyph` + capitalized label, colored by tier — the worst-first row
/// marker (reads at a glance even monochrome).
pub fn tier_marker(tier: Tier, enabled: bool) -> String {
    let body = format!("{} {}", tier_glyph(tier), tier.label());
    paint(tier_code(tier), &body, enabled)
}

/// Paint arbitrary text (e.g. a pre-padded cell) in a tier's color. Lets a
/// caller align columns on the plain text, then colorize without breaking width.
pub fn tier_paint(tier: Tier, text: &str, enabled: bool) -> String {
    paint(tier_code(tier), text, enabled)
}

/// Paint arbitrary text in a 0–100 score band's color.
pub fn score_paint(score: u8, text: &str, enabled: bool) -> String {
    paint(score_color_code(score), text, enabled)
}

/// An OSC 8 hyperlink (`text` linking to `url`) when stdout is an interactive
/// TTY, else the bare `text`. Callers also print the literal URL so logs/pipes
/// keep it.
pub fn hyperlink(url: &str, text: &str, enabled_tty: bool) -> String {
    if enabled_tty {
        format!("\x1b]8;;{url}\x1b\\{text}\x1b]8;;\x1b\\")
    } else {
        text.to_string()
    }
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

    #[test]
    fn score_color_band_edges() {
        // Band edges: 39/40 (red→orange), 59/60 (orange→yellow), 79/80 (→green).
        assert_eq!(score_color_code(39), "31");
        assert_eq!(score_color_code(40), "38;5;208");
        assert_eq!(score_color_code(59), "38;5;208");
        assert_eq!(score_color_code(60), "33");
        assert_eq!(score_color_code(79), "33");
        assert_eq!(score_color_code(80), "32");
        assert_eq!(score_color_code(100), "32");
        assert_eq!(score_color_code(0), "31");
    }

    #[test]
    fn bar_gauge_plain_when_color_off() {
        let g = bar_gauge(60, 10, false);
        assert!(!g.contains("\x1b["), "no ANSI when color off");
        // 60% of 10 → 6 filled, 4 empty.
        assert_eq!(g.chars().filter(|c| *c == '\u{2588}').count(), 6);
        assert_eq!(g.chars().filter(|c| *c == '\u{2591}').count(), 4);
    }

    #[test]
    fn bar_gauge_rounds_and_clamps() {
        // 0 → all empty; 100 → all filled; over-100 clamps.
        assert_eq!(
            bar_gauge(0, 10, false)
                .chars()
                .filter(|c| *c == '\u{2588}')
                .count(),
            0
        );
        assert_eq!(
            bar_gauge(100, 10, false)
                .chars()
                .filter(|c| *c == '\u{2588}')
                .count(),
            10
        );
        assert_eq!(
            bar_gauge(200, 10, false)
                .chars()
                .filter(|c| *c == '\u{2588}')
                .count(),
            10
        );
    }

    #[test]
    fn tier_glyph_is_distinct_per_tier() {
        assert_eq!(tier_glyph(Tier::Green), '\u{25cf}');
        assert_eq!(tier_glyph(Tier::Red), '\u{2717}');
        assert_ne!(tier_glyph(Tier::Yellow), tier_glyph(Tier::Orange));
        assert_eq!(tier_glyph(Tier::Unscoped), tier_glyph(Tier::Unknown));
    }

    #[test]
    fn tier_marker_carries_label_without_color() {
        let m = tier_marker(Tier::Orange, false);
        assert!(m.contains("Orange"));
        assert!(m.contains('\u{25d1}'));
        assert!(!m.contains("\x1b["));
    }

    #[test]
    fn hyperlink_bare_url_when_not_tty() {
        assert_eq!(hyperlink("https://x.test", "View", false), "View");
        let osc = hyperlink("https://x.test", "View", true);
        assert!(osc.contains("https://x.test"));
        assert!(osc.contains("\x1b]8;;"));
    }
}
