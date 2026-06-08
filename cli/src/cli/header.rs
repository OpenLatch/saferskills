//! The SaferSkills CLI banner.
//!
//! Two compact lines, both to **stderr**, suppressed in Json / quiet:
//!
//! ```text
//! ▄▄▄ SaferSkills ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
//!     v0.1.0 · An OpenLatch project
//! ```
//!
//! Line 1 is the brand rule — sized to span the **exact terminal width** and
//! tinted a fresh, calm tone from a curated palette (§ [`PALETTE`]) on every
//! invocation, so it gently varies run to run without ever shouting. Plain
//! `=== SaferSkills ===…=` when colour is off. Line 2 is the version followed by
//! the single permitted OpenLatch attribution, dimmed so the bar stays the hero.
//!
//! Brand rules (`.claude/rules/design-system.md`): the wordmark is ALWAYS
//! camelCase `SaferSkills`; `An OpenLatch project` is the ONLY OpenLatch string
//! permitted anywhere in CLI output (anti-recommendation — no other OpenLatch
//! reference in any banner/help/error).

use terminal_size::{terminal_size, Width};

use crate::cli::color;
use crate::cli::output::{OutputConfig, OutputFormat};

/// Brand label rendered between the leading and trailing fill (with padding).
const LABEL: &str = " SaferSkills ";
/// Leading fill glyph count.
const LEAD: usize = 3;
/// Fallback width when the terminal size can't be detected (non-TTY / piped /
/// redirected stderr) and `COLUMNS` is unset.
const FALLBACK_WIDTH: usize = 80;

/// Curated palette of calm, non-aggressive 256-colour foreground codes. Weighted
/// to the SaferSkills emerald-teal family and its cool neighbours — teal, sage,
/// dusty blue, slate lavender, aqua. Deliberately NO hot reds / oranges /
/// magentas: every entry is a muted, desaturated tone. One is chosen per
/// invocation so the bar shifts subtly between runs.
const PALETTE: &[u8] = &[
    36,  // teal-cyan (the original)
    37,  // teal
    66,  // muted teal-gray
    72,  // green-teal
    73,  // soft cyan-blue
    79,  // aqua
    67,  // steel blue
    108, // sage green
    109, // dusty cyan
    110, // soft slate-blue
    103, // slate lavender
    115, // pale green
];

/// Pick a palette colour for this run. Seeded from the wall-clock nanos mixed
/// with the PID, run through a splitmix64 finaliser so even the coarse Windows
/// clock (and PID-aligned process spacing) avalanches into a well-spread index —
/// no RNG dependency, just bit-mixing.
fn pick_color() -> u8 {
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos() as u64)
        .unwrap_or(0);
    let mut x = nanos ^ ((std::process::id() as u64) << 32);
    x = x.wrapping_add(0x9E37_79B9_7F4A_7C15);
    x = (x ^ (x >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    x = (x ^ (x >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    x ^= x >> 31;
    PALETTE[(x as usize) % PALETTE.len()]
}

/// Detect the terminal column count so the rule spans the full width. Prefers
/// the real terminal size (queried on stderr — where the banner renders), then
/// `COLUMNS`, then a sane fallback.
fn detect_width() -> usize {
    if let Some((Width(w), _)) = terminal_size() {
        if w > 0 {
            return usize::from(w);
        }
    }
    std::env::var("COLUMNS")
        .ok()
        .and_then(|v| v.trim().parse::<usize>().ok())
        .filter(|w| *w > 0)
        .unwrap_or(FALLBACK_WIDTH)
}

/// Build the brand rule occupying exactly `width` columns:
/// `▄▄▄ SaferSkills ▄…▄` (colour) or `=== SaferSkills ===…=` (plain). `width` is
/// clamped up to the minimum that fits the label; otherwise it is honoured
/// exactly. `color_code` is the chosen 256-colour code, ignored when `color` is
/// false.
fn build_rule(width: usize, color: bool, color_code: u8) -> String {
    let min_width = LEAD + LABEL.chars().count() + 1;
    let width = width.max(min_width);

    let fill = if color { '\u{2584}' } else { '=' };
    let lead: String = std::iter::repeat_n(fill, LEAD).collect();
    let tail_len = width - LEAD - LABEL.chars().count();
    let tail: String = std::iter::repeat_n(fill, tail_len).collect();

    if color {
        format!("\x1b[38;5;{color_code}m{lead}{LABEL}{tail}\x1b[0m")
    } else {
        format!("{lead}{LABEL}{tail}")
    }
}

/// Print the two-line banner to stderr: the full-width, freshly-tinted brand
/// rule, then the dimmed `v{version} · An OpenLatch project` line. Suppressed in
/// Json / quiet.
pub fn print(output: &OutputConfig) {
    if output.format == OutputFormat::Json || output.quiet {
        return;
    }
    eprintln!("{}", build_rule(detect_width(), output.color, pick_color()));

    let version = env!("CARGO_PKG_VERSION");
    let meta = format!("    v{version} · An OpenLatch project");
    eprintln!("{}", color::dim(&meta, output.color));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rule_contains_camelcase_wordmark() {
        assert!(build_rule(80, false, 36).contains("SaferSkills"));
        assert!(build_rule(80, true, 36).contains("SaferSkills"));
    }

    #[test]
    fn plain_rule_spans_exact_width() {
        // The visible rule is exactly `width` columns — no max clamp.
        assert_eq!(build_rule(80, false, 36).chars().count(), 80);
        assert_eq!(build_rule(200, false, 36).chars().count(), 200);
    }

    #[test]
    fn narrow_width_clamps_up_to_fit_label() {
        // A width too small for the label is bumped to the minimum that fits.
        let min_width = LEAD + LABEL.chars().count() + 1;
        assert_eq!(build_rule(1, false, 36).chars().count(), min_width);
    }

    #[test]
    fn plain_rule_has_no_ansi() {
        assert!(!build_rule(80, false, 36).contains("\x1b["));
    }

    #[test]
    fn colored_rule_uses_256color_escape() {
        // Every palette entry must render as a 256-colour foreground escape.
        for &code in PALETTE {
            let rule = build_rule(80, true, code);
            assert!(rule.starts_with(&format!("\x1b[38;5;{code}m")));
            assert!(rule.ends_with("\x1b[0m"));
        }
    }

    #[test]
    fn picked_color_is_always_in_palette() {
        // Whatever the seed, the chosen code is one of the curated tones.
        for _ in 0..256 {
            assert!(PALETTE.contains(&pick_color()));
        }
    }

    #[test]
    fn palette_excludes_aggressive_codes() {
        // Guard against a future edit slipping in a hot red/orange/magenta.
        const AGGRESSIVE: &[u8] = &[9, 196, 160, 124, 202, 208, 214, 13, 201, 165, 199];
        for code in AGGRESSIVE {
            assert!(!PALETTE.contains(code), "palette must stay non-aggressive");
        }
    }
}
