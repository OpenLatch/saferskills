//! Consent resolver for the crash-report subsystem.
//!
//! Precedence (top wins) — crash reports are diagnostic, so they default ON,
//! but they honour the SAME universal opt-out envs as PostHog telemetry
//! (`core::telemetry`) so a single env silences everything:
//!
//! 1. `SENTRY_DISABLED` / `SAFERSKILLS_NO_CRASH_REPORT` env — hard lock
//! 2. Any universal opt-out env (`CI` / `DO_NOT_TRACK` /
//!    `SAFERSKILLS_NO_TELEMETRY`) — same kill-switches that silence the PostHog
//!    leg, so "opt out once, opt out of everything" holds
//! 3. DSN missing (empty at both compile and runtime) → disabled (no-op)
//! 4. `[crashreport] enabled = false` in `~/.saferskills/config.toml` → disabled
//! 5. Section missing or `enabled = true` → **enabled** (default-on)
//!
//! A corrupt `config.toml` is treated as "default on" — a parse error must not
//! silently stop crash diagnostics (the operator needs to see panics to fix
//! them). This mirrors openlatch-client's crash-report consent.

use std::path::Path;

use super::config::read_section;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConsentState {
    Enabled,
    Disabled,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DecidedBy {
    /// `SENTRY_DISABLED` / `SAFERSKILLS_NO_CRASH_REPORT` is set.
    DisabledEnv,
    /// A universal opt-out env (`CI` / `DO_NOT_TRACK` / `SAFERSKILLS_NO_TELEMETRY`).
    UniversalOptOut,
    /// No DSN baked at build time and none provided at runtime.
    NoBakedDsn,
    /// `[crashreport] enabled = false` in `config.toml`.
    ConfigFile,
    /// Default path — section absent or explicitly `enabled = true`.
    DefaultEnabled,
}

#[derive(Debug, Clone, Copy)]
pub struct Resolved {
    pub state: ConsentState,
    // Diagnostic provenance — asserted in tests, surfaced for future
    // `doctor`-style introspection. Not read on the production `init` path
    // (which only branches on `state`), hence the allow.
    #[allow(dead_code)]
    pub decided_by: DecidedBy,
}

impl Resolved {
    pub fn enabled(&self) -> bool {
        self.state == ConsentState::Enabled
    }

    fn disabled(decided_by: DecidedBy) -> Self {
        Self {
            state: ConsentState::Disabled,
            decided_by,
        }
    }
}

/// Resolve consent for the crash-report subsystem.
///
/// `config_path` is the full path to `~/.saferskills/config.toml`.
/// `dsn_present` is the runtime view of "do we have a usable DSN string".
pub fn resolve(config_path: &Path, dsn_present: bool) -> Resolved {
    if is_truthy_env("SENTRY_DISABLED") || is_truthy_env("SAFERSKILLS_NO_CRASH_REPORT") {
        return Resolved::disabled(DecidedBy::DisabledEnv);
    }
    // The universal kill-switches that also silence PostHog telemetry. Honoured
    // here so a single opt-out covers both legs (telemetry.rs::opted_out_env).
    if env_present("SAFERSKILLS_NO_TELEMETRY") || env_present("DO_NOT_TRACK") || env_present("CI") {
        return Resolved::disabled(DecidedBy::UniversalOptOut);
    }
    if !dsn_present {
        return Resolved::disabled(DecidedBy::NoBakedDsn);
    }
    match read_section(config_path) {
        Ok(Some(section)) if !section.enabled => Resolved::disabled(DecidedBy::ConfigFile),
        // Section present with enabled=true → ConfigFile-enabled; absent or a
        // parse error → DefaultEnabled. A parse error is NOT "disabled" (a
        // corrupt file shouldn't silently kill crash diagnostics).
        Ok(Some(_)) => Resolved {
            state: ConsentState::Enabled,
            decided_by: DecidedBy::ConfigFile,
        },
        Ok(None) | Err(_) => Resolved {
            state: ConsentState::Enabled,
            decided_by: DecidedBy::DefaultEnabled,
        },
    }
}

fn env_present(key: &str) -> bool {
    std::env::var_os(key).is_some_and(|v| !v.is_empty())
}

fn is_truthy_env(name: &str) -> bool {
    match std::env::var(name) {
        Ok(v) => {
            let v = v.trim().to_ascii_lowercase();
            !matches!(v.as_str(), "" | "0" | "false" | "no" | "off")
        }
        Err(_) => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;
    use tempfile::TempDir;

    // env vars are process-global; serialize tests that touch them.
    static ENV_LOCK: Mutex<()> = Mutex::new(());

    const ENVS: &[&str] = &[
        "SENTRY_DISABLED",
        "SAFERSKILLS_NO_CRASH_REPORT",
        "SAFERSKILLS_NO_TELEMETRY",
        "DO_NOT_TRACK",
        "CI",
    ];

    fn with_clean_env<F: FnOnce()>(f: F) {
        let _g = ENV_LOCK.lock().unwrap_or_else(|p| p.into_inner());
        for k in ENVS {
            std::env::remove_var(k);
        }
        f();
        for k in ENVS {
            std::env::remove_var(k);
        }
    }

    #[test]
    fn disabled_when_sentry_disabled_env_set() {
        with_clean_env(|| {
            std::env::set_var("SENTRY_DISABLED", "1");
            let tmp = TempDir::new().unwrap();
            let r = resolve(&tmp.path().join("config.toml"), true);
            assert_eq!(r.state, ConsentState::Disabled);
            assert_eq!(r.decided_by, DecidedBy::DisabledEnv);
        });
    }

    #[test]
    fn disabled_when_universal_opt_out_set() {
        with_clean_env(|| {
            std::env::set_var("DO_NOT_TRACK", "1");
            let tmp = TempDir::new().unwrap();
            let r = resolve(&tmp.path().join("config.toml"), true);
            assert_eq!(r.state, ConsentState::Disabled);
            assert_eq!(r.decided_by, DecidedBy::UniversalOptOut);
        });
    }

    #[test]
    fn disabled_when_no_dsn() {
        with_clean_env(|| {
            let tmp = TempDir::new().unwrap();
            let r = resolve(&tmp.path().join("config.toml"), false);
            assert_eq!(r.state, ConsentState::Disabled);
            assert_eq!(r.decided_by, DecidedBy::NoBakedDsn);
        });
    }

    #[test]
    fn disabled_when_config_says_false() {
        with_clean_env(|| {
            let tmp = TempDir::new().unwrap();
            let p = tmp.path().join("config.toml");
            std::fs::write(&p, "[crashreport]\nenabled = false\n").unwrap();
            let r = resolve(&p, true);
            assert_eq!(r.state, ConsentState::Disabled);
            assert_eq!(r.decided_by, DecidedBy::ConfigFile);
        });
    }

    #[test]
    fn enabled_by_default_when_config_missing() {
        with_clean_env(|| {
            let tmp = TempDir::new().unwrap();
            let r = resolve(&tmp.path().join("config.toml"), true);
            assert!(r.enabled());
            assert_eq!(r.decided_by, DecidedBy::DefaultEnabled);
        });
    }

    #[test]
    fn enabled_when_config_says_true() {
        with_clean_env(|| {
            let tmp = TempDir::new().unwrap();
            let p = tmp.path().join("config.toml");
            std::fs::write(&p, "[crashreport]\nenabled = true\n").unwrap();
            let r = resolve(&p, true);
            assert!(r.enabled());
            assert_eq!(r.decided_by, DecidedBy::ConfigFile);
        });
    }
}
