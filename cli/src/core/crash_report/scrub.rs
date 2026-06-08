//! `before_send` scrubber — redacts credentials and user paths from panic
//! messages and backtrace frames before any event leaves the process.
//!
//! Self-contained (no `regex` dependency — keeps the release binary lean under
//! the `cli-build` size gate). The matchers are simple byte scanners that find
//! a known credential **prefix** then consume the trailing token charset; the
//! whole match is replaced with a labeled placeholder (`[AWS_KEY:AKIA***]`,
//! `[GITHUB_TOKEN:ghp_***]`, …). This is the SaferSkills analogue of
//! openlatch-client's `privacy` module, scoped to exactly what a crash report
//! can carry.
//!
//! Fields scrubbed:
//! - `event.message`
//! - `event.exception.values[*].value` (panic message)
//! - `event.exception.values[*].stacktrace.frames[*].filename`
//! - `event.exception.values[*].stacktrace.frames[*].function`
//!
//! `send_default_pii = false` (set in `mod.rs`) already drops server-name /
//! username context; this scrubber is the second line for content that a panic
//! message might interpolate.

use sentry::protocol::Event;

/// Scrub an outgoing Sentry event in place.
///
/// Always returns `Some(event)` — we never drop events (an opaque redacted
/// stack trace still dedupes by fingerprint and remains useful for triage).
pub fn scrub_event(mut event: Event<'static>) -> Option<Event<'static>> {
    if let Some(ref mut msg) = event.message {
        *msg = scrub_string(msg);
    }
    for exception in event.exception.iter_mut() {
        if let Some(ref mut v) = exception.value {
            *v = scrub_string(v);
        }
        if let Some(ref mut st) = exception.stacktrace {
            for frame in st.frames.iter_mut() {
                if let Some(ref mut f) = frame.filename {
                    *f = scrub_string(f);
                }
                if let Some(ref mut f) = frame.function {
                    *f = scrub_string(f);
                }
            }
        }
    }
    Some(event)
}

/// A credential matcher: a literal prefix + how many bytes of it to keep as a
/// public hint + the charset of the trailing token + a minimum token length.
struct Pattern {
    prefix: &'static str,
    label: &'static str,
    /// Bytes of the matched prefix to preserve in the mask (0 = none).
    keep: usize,
    /// Minimum count of trailing token chars required for a real match.
    min_tail: usize,
    /// Predicate over a trailing token byte.
    tail: fn(u8) -> bool,
}

fn alnum(b: u8) -> bool {
    b.is_ascii_alphanumeric()
}
fn alnum_underscore(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_'
}
fn token_charset(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_' || b == b'-'
}

/// Ordered most-specific-first so a longer prefix wins over a shorter one that
/// shares its head (e.g. `github_pat_` before `ghp_`, `sk_live_` before `sk-`).
const PATTERNS: &[Pattern] = &[
    Pattern {
        prefix: "AKIA",
        label: "AWS_KEY",
        keep: 4,
        min_tail: 16,
        tail: alnum,
    },
    Pattern {
        prefix: "github_pat_",
        label: "GITHUB_TOKEN",
        keep: 11,
        min_tail: 20,
        tail: alnum_underscore,
    },
    Pattern {
        prefix: "ghp_",
        label: "GITHUB_TOKEN",
        keep: 4,
        min_tail: 20,
        tail: alnum,
    },
    Pattern {
        prefix: "gho_",
        label: "GITHUB_TOKEN",
        keep: 4,
        min_tail: 20,
        tail: alnum,
    },
    Pattern {
        prefix: "sk_live_",
        label: "STRIPE_KEY",
        keep: 8,
        min_tail: 16,
        tail: alnum,
    },
    Pattern {
        prefix: "sk_test_",
        label: "STRIPE_KEY",
        keep: 8,
        min_tail: 16,
        tail: alnum,
    },
    Pattern {
        prefix: "sk-ant-",
        label: "ANTHROPIC_KEY",
        keep: 7,
        min_tail: 16,
        tail: token_charset,
    },
    Pattern {
        prefix: "sk-proj-",
        label: "OPENAI_KEY",
        keep: 8,
        min_tail: 20,
        tail: token_charset,
    },
    Pattern {
        prefix: "sk-",
        label: "OPENAI_KEY",
        keep: 3,
        min_tail: 32,
        tail: alnum,
    },
    Pattern {
        prefix: "xoxb-",
        label: "SLACK_TOKEN",
        keep: 5,
        min_tail: 10,
        tail: token_charset,
    },
    Pattern {
        prefix: "xoxp-",
        label: "SLACK_TOKEN",
        keep: 5,
        min_tail: 10,
        tail: token_charset,
    },
];

/// Scrub one string: mask credentials, then redact a user-home path prefix.
fn scrub_string(s: &str) -> String {
    let masked = mask_credentials(s);
    redact_home(&masked)
}

/// Scan `s` for any credential pattern and replace each whole match with a
/// labeled placeholder. Single left-to-right pass; at each index the first
/// (most-specific) matching prefix wins.
fn mask_credentials(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out = String::with_capacity(s.len());
    let mut i = 0;
    'outer: while i < bytes.len() {
        for p in PATTERNS {
            let pl = p.prefix.len();
            if i + pl <= bytes.len() && &bytes[i..i + pl] == p.prefix.as_bytes() {
                // Count the trailing token chars after the prefix.
                let mut j = i + pl;
                while j < bytes.len() && (p.tail)(bytes[j]) {
                    j += 1;
                }
                if j - (i + pl) >= p.min_tail {
                    if p.keep > 0 {
                        out.push('[');
                        out.push_str(p.label);
                        out.push(':');
                        out.push_str(&s[i..i + p.keep]);
                        out.push_str("***]");
                    } else {
                        out.push('[');
                        out.push_str(p.label);
                        out.push_str(":***]");
                    }
                    i = j;
                    continue 'outer;
                }
            }
        }
        // No match at i: copy this UTF-8 char verbatim. `bytes[i]` is always a
        // char boundary here (we only ever jump `i` to a boundary `j`).
        let ch_len = utf8_len(bytes[i]);
        out.push_str(&s[i..i + ch_len]);
        i += ch_len;
    }
    out
}

/// Byte length of the UTF-8 char starting at a leading byte.
fn utf8_len(b: u8) -> usize {
    if b < 0x80 {
        1
    } else if b >> 5 == 0b110 {
        2
    } else if b >> 4 == 0b1110 {
        3
    } else if b >> 3 == 0b11110 {
        4
    } else {
        1 // continuation/invalid — advance one to avoid stalling
    }
}

/// Replace an absolute user-home directory prefix with `~`. Covers the common
/// Unix (`/home/<user>`, `/Users/<user>`) and Windows (`C:\Users\<user>`)
/// shapes so a backtrace `filename` never leaks the developer/user account name.
fn redact_home(s: &str) -> String {
    let mut out = s.to_string();
    for (prefix, sep) in [("/home/", '/'), ("/Users/", '/')] {
        out = redact_segment(&out, prefix, sep);
    }
    // Windows: \Users\<name>\  and  /Users/<name>/ already handled above for /.
    out = redact_segment(&out, "\\Users\\", '\\');
    out
}

/// Find each `prefix<segment><sep>` and rewrite it to `~<sep>`, dropping the one
/// account-name segment that follows the prefix.
fn redact_segment(s: &str, prefix: &str, sep: char) -> String {
    let mut out = String::with_capacity(s.len());
    let mut rest = s;
    while let Some(pos) = rest.find(prefix) {
        out.push_str(&rest[..pos]);
        let after = &rest[pos + prefix.len()..];
        match after.find(sep) {
            Some(end) => {
                out.push('~');
                out.push(sep);
                rest = &after[end + sep.len_utf8()..];
            }
            None => {
                // Trailing `prefix<name>` with no further separator → ~.
                out.push('~');
                rest = "";
            }
        }
    }
    out.push_str(rest);
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use sentry::protocol::{Exception, Frame, Stacktrace, Values};

    fn panic_event(message: &str) -> Event<'static> {
        Event {
            exception: Values::from(vec![Exception {
                ty: "panic".into(),
                value: Some(message.to_string()),
                ..Default::default()
            }]),
            ..Default::default()
        }
    }

    #[test]
    fn redacts_aws_key_in_panic_message() {
        // Synthetic pattern-matching fixture, not a real credential.
        let fake = format!("{}{}", "AKIA", "1234567890ABCDEF"); // gitleaks:allow
        let ev = panic_event(&format!("boom: {fake} leaked"));
        let out = scrub_event(ev).unwrap();
        let v = out.exception[0].value.as_ref().unwrap();
        assert!(v.contains("[AWS_KEY:AKIA***]"), "got: {v}");
        assert!(!v.contains(&fake));
    }

    #[test]
    fn redacts_github_ghp_token() {
        let tok = format!("ghp_{}", "a".repeat(36));
        let ev = panic_event(&format!("token {tok}"));
        let out = scrub_event(ev).unwrap();
        let v = out.exception[0].value.as_ref().unwrap();
        assert!(v.contains("[GITHUB_TOKEN:ghp_***]"), "got: {v}");
        assert!(!v.contains(&tok));
    }

    #[test]
    fn redacts_github_pat_before_ghp() {
        let tok = format!("github_pat_{}", "a".repeat(82));
        let ev = panic_event(&tok);
        let out = scrub_event(ev).unwrap();
        let v = out.exception[0].value.as_ref().unwrap();
        assert_eq!(v, "[GITHUB_TOKEN:github_pat_***]");
    }

    #[test]
    fn redacts_openai_key() {
        let key = format!("sk-{}", "a".repeat(48));
        let ev = panic_event(&key);
        let out = scrub_event(ev).unwrap();
        let v = out.exception[0].value.as_ref().unwrap();
        assert_eq!(v, "[OPENAI_KEY:sk-***]");
    }

    #[test]
    fn redacts_stripe_live_before_generic() {
        let key = format!("sk_live_{}", "a".repeat(24));
        let ev = panic_event(&key);
        let out = scrub_event(ev).unwrap();
        let v = out.exception[0].value.as_ref().unwrap();
        assert_eq!(v, "[STRIPE_KEY:sk_live_***]");
    }

    #[test]
    fn redacts_home_path_in_frame_filename() {
        let mut ev = panic_event("boom");
        ev.exception[0].stacktrace = Some(Stacktrace {
            frames: vec![Frame {
                filename: Some("/home/alice/proj/main.rs".into()),
                function: Some("my_fn".into()),
                ..Default::default()
            }],
            ..Default::default()
        });
        let out = scrub_event(ev).unwrap();
        let fname = out.exception[0].stacktrace.as_ref().unwrap().frames[0]
            .filename
            .as_ref()
            .unwrap();
        assert_eq!(fname, "~/proj/main.rs");
        assert!(!fname.contains("alice"));
    }

    #[test]
    fn redacts_windows_home_path() {
        let ev = panic_event("at C:\\Users\\bob\\.saferskills\\config.toml");
        let out = scrub_event(ev).unwrap();
        let v = out.exception[0].value.as_ref().unwrap();
        assert!(v.contains("C:~\\.saferskills"), "got: {v}");
        assert!(!v.contains("bob"));
    }

    #[test]
    fn preserves_event_with_no_secrets() {
        let ev = panic_event("ordinary panic, no secrets");
        let out = scrub_event(ev).unwrap();
        assert_eq!(
            out.exception[0].value.as_ref().unwrap(),
            "ordinary panic, no secrets"
        );
    }

    #[test]
    fn short_sk_prefix_is_not_a_false_positive() {
        // "sk-short" is too short for the 32-char min tail → left intact.
        let ev = panic_event("disk-something sk-short");
        let out = scrub_event(ev).unwrap();
        assert_eq!(
            out.exception[0].value.as_ref().unwrap(),
            "disk-something sk-short"
        );
    }

    #[test]
    fn masks_multiple_secrets_in_one_string() {
        let aws = format!("{}{}", "AKIA", "1111111111111111"); // gitleaks:allow
        let ghp = format!("ghp_{}", "b".repeat(36));
        let ev = panic_event(&format!("a={aws} b={ghp}"));
        let out = scrub_event(ev).unwrap();
        let v = out.exception[0].value.as_ref().unwrap();
        assert!(v.contains("[AWS_KEY:AKIA***]"));
        assert!(v.contains("[GITHUB_TOKEN:ghp_***]"));
        assert!(!v.contains(&aws) && !v.contains(&ghp));
    }

    #[test]
    fn handles_multibyte_utf8_without_panicking() {
        let ev = panic_event("crème brûlée 🦀 panicked at sk-short");
        let out = scrub_event(ev).unwrap();
        let v = out.exception[0].value.as_ref().unwrap();
        assert!(v.contains("🦀"));
        assert!(v.contains("crème brûlée"));
    }
}
