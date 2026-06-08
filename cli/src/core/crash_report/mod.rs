//! Crash reporting subsystem — forwards Rust panics to Sentry.
//!
//! Scope is deliberately narrow: panics only, scrubbed by [`scrub`] before
//! transport, never any artifact content (`.claude/rules/telemetry.md` § Sentry:
//! errors-only, no-PII, separate SaferSkills project). Mirrors
//! openlatch-client's crash_report module.
//!
//! The whole module is feature-gated behind `crash-report`. When the feature is
//! absent a no-op shim (bottom of this file) exposes the SAME public surface so
//! `main.rs` compiles unchanged in both configs and the `sentry` dep drops from
//! the graph.
//!
//! ## Panic strategy
//!
//! The release profile uses **unwind** (no `panic = "abort"` — see `Cargo.toml`),
//! so sentry's `panic` integration installs its own hook during [`init`] and
//! captures a full backtrace automatically. [`install_panic_hook`] additionally
//! chains a SaferSkills hook that tags the panic location, then calls the
//! previous (sentry) hook so both fire.

// The submodule files live directly in `crash_report/`. They are declared at
// this top level — NOT inside the inline `imp` module — so each resolves to
// `crash_report/<file>.rs`. A `#[path = "../config.rs"]` on a module declared
// *inside* `mod imp` resolves relative to the inline module's virtual directory,
// i.e. `crash_report/imp/../config.rs`: that normalizes lexically on Windows but
// fails on Linux, where `imp/` is not a real directory the kernel can resolve
// `..` through (the cli-fmt/clippy/test CI lanes run on Linux).
#[cfg(feature = "crash-report")]
mod config;
#[cfg(feature = "crash-report")]
mod consent;
#[cfg(feature = "crash-report")]
mod scrub;

#[cfg(feature = "crash-report")]
mod imp {
    use std::sync::Arc;
    use std::time::Duration;

    use sentry::{ClientInitGuard, ClientOptions};

    use crate::core::config::config_path;

    use super::consent::resolve;

    /// Baked DSN from `build.rs`. Empty string when unset at build time (dev /
    /// fork / `cargo install` with no secret) — [`resolve_dsn`] then yields
    /// `None` and [`init`] is a no-op (the same "no baked key ⇒ silent no-op"
    /// discipline as `core::telemetry`).
    const BAKED_DSN: &str = env!("SAFERSKILLS_SENTRY_DSN");

    /// Baked release identifier from `build.rs` (git SHA in CI, else the crate
    /// version). Used as `release = "saferskills-cli@{release}"`.
    const BAKED_RELEASE: &str = env!("SAFERSKILLS_RELEASE");

    /// Resolve the DSN: runtime env wins (so CI / tests can point at a mock
    /// endpoint without rebuilding), else the baked value. Empty in both → None.
    fn resolve_dsn() -> Option<String> {
        std::env::var("SAFERSKILLS_SENTRY_DSN")
            .ok()
            .filter(|s| !s.is_empty())
            .or_else(|| {
                if BAKED_DSN.is_empty() {
                    None
                } else {
                    Some(BAKED_DSN.to_string())
                }
            })
    }

    /// Initialize Sentry for the current process.
    ///
    /// Returns `Some(guard)` when crash reporting is active — the caller must
    /// hold the guard for the program lifetime (its `Drop` flushes pending
    /// events with a 2s deadline). Returns `None` when disabled by any consent
    /// rule (no DSN, opt-out env, or `[crashreport] enabled = false`);
    /// subsequent `enrich_*` / `flush` calls are no-ops in that state.
    ///
    /// Must run **before** the tokio runtime is built and before clap parses
    /// args, so panics during runtime construction / arg parsing are captured.
    pub fn init() -> Option<ClientInitGuard> {
        let dsn = resolve_dsn();
        let decision = resolve(&config_path(), dsn.is_some());
        if !decision.enabled() {
            return None;
        }
        // A malformed DSN parses to None → treat as disabled. We never unwrap
        // and never panic on startup for a misconfigured DSN.
        let parsed = dsn.as_deref().and_then(|s| s.parse().ok());
        parsed.as_ref()?;

        let release = format!("saferskills-cli@{BAKED_RELEASE}");
        let environment = if cfg!(debug_assertions) {
            "development"
        } else {
            "production"
        };

        let options = ClientOptions {
            dsn: parsed,
            release: Some(release.into()),
            environment: Some(environment.into()),
            send_default_pii: false,
            traces_sample_rate: 0.0,
            attach_stacktrace: true,
            // Scrub every outgoing event (panic message + backtrace frames).
            before_send: Some(Arc::new(super::scrub::scrub_event)),
            ..Default::default()
        };

        Some(sentry::init(options))
    }

    /// Tag the current Hub scope as a CLI invocation. No-op when crash reporting
    /// was never initialized (Hub has no client). `command` is the closed-enum
    /// grammar label — never a flag value (same no-PII discipline as telemetry).
    pub fn enrich_cli_scope(command: &str, subcommand: Option<&str>) {
        sentry::configure_scope(|scope| {
            scope.set_tag("process_type", "cli");
            scope.set_tag("command", command);
            if let Some(sub) = subcommand {
                scope.set_tag("subcommand", sub);
            }
        });
    }

    /// Chain a SaferSkills panic hook onto sentry's (installed during [`init`]).
    /// Ours tags only the `file:line` panic location — never the message or any
    /// interpolated value — then calls the previous hook so sentry still
    /// captures the event.
    pub fn install_panic_hook() {
        let prev = std::panic::take_hook();
        std::panic::set_hook(Box::new(move |info| {
            let location = info
                .location()
                .map(|l| format!("{}:{}", l.file(), l.line()))
                .unwrap_or_else(|| "unknown".to_string());
            sentry::configure_scope(|scope| {
                scope.set_tag("panic_location", &location);
            });
            prev(info);
        }));
    }

    /// Best-effort synchronous flush of pending events. Used from the ctrlc
    /// handler before `process::exit(130)` (which skips `Drop`). No-op when
    /// crash reporting is disabled.
    pub fn flush(timeout: Duration) {
        if let Some(client) = sentry::Hub::current().client() {
            let _ = client.flush(Some(timeout));
        }
    }
}

#[cfg(feature = "crash-report")]
pub use imp::{enrich_cli_scope, flush, init, install_panic_hook};

// ---------------------------------------------------------------------------
// No-op shim — compiled when `crash-report` is OFF so `main.rs` calls type-check
// in both configs and the `sentry` dep is dropped from the graph entirely.
// ---------------------------------------------------------------------------
#[cfg(not(feature = "crash-report"))]
mod shim {
    use std::time::Duration;

    /// Opaque guard placeholder when crash reporting is compiled out.
    pub struct ClientInitGuard;

    /// No-op: returns `None` (no Sentry client linked).
    pub fn init() -> Option<ClientInitGuard> {
        None
    }

    /// No-op.
    pub fn enrich_cli_scope(_command: &str, _subcommand: Option<&str>) {}

    /// No-op.
    pub fn install_panic_hook() {}

    /// No-op.
    pub fn flush(_timeout: Duration) {}
}

#[cfg(not(feature = "crash-report"))]
pub use shim::{enrich_cli_scope, flush, init, install_panic_hook, ClientInitGuard};
