//! Opt-out anonymous usage analytics (D-05-13) — mirrors openlatch-client.
//!
//! - The PostHog project key is **baked at build time** by `build.rs`
//!   (`SAFERSKILLS_POSTHOG_KEY`). Empty (dev / forks) ⇒ a hard no-op: the
//!   `command_invoked` event is computed but never sent.
//! - A single `command_invoked` event carries a CLOSED-ENUM `(command,
//!   subcommand)` label derived from the grammar — NEVER a flag value — plus
//!   the exit code and a coarse duration bucket. No PII, ever.
//! - Universal opt-out: `SAFERSKILLS_NO_TELEMETRY` / `DO_NOT_TRACK` / `CI`
//!   (any non-empty value), or the `telemetry = false` config key.
//! - The network POST is gated behind the `telemetry-network` feature (a blip
//!   must never delay or fail a user command; the send is best-effort with a
//!   tight timeout).
//! - First-run disclosure prints ONCE (sentinel-gated), only in interactive
//!   human mode; suppressed under `--json` / `--quiet` / non-TTY / CI.

use std::io::IsTerminal;

use crate::cli::output::OutputConfig;
use crate::core::config::saferskills_dir;

/// The PostHog project key baked by `build.rs` (empty when unset).
pub const fn baked_key() -> &'static str {
    env!("SAFERSKILLS_POSTHOG_KEY")
}

/// The PostHog host baked by `build.rs`. Only referenced by the gated network
/// send path, so it is compiled in only under the `telemetry-network` feature.
#[cfg(feature = "telemetry-network")]
const POSTHOG_HOST: &str = env!("SAFERSKILLS_POSTHOG_HOST");

/// Sentinel filename marking that the first-run notice has been shown.
const NOTICE_SENTINEL: &str = ".telemetry-notice";

fn env_present(key: &str) -> bool {
    std::env::var_os(key).is_some_and(|v| !v.is_empty())
}

/// Whether any universal opt-out env var is set.
fn opted_out_env() -> bool {
    env_present("SAFERSKILLS_NO_TELEMETRY") || env_present("DO_NOT_TRACK") || env_present("CI")
}

/// Whether analytics will actually be sent: config allows it, no env opt-out,
/// AND a key was baked in (no key ⇒ never any network, D-05-13).
pub fn is_enabled(config_allows: bool) -> bool {
    config_allows && !opted_out_env() && !baked_key().is_empty()
}

/// Coarse duration bucket — avoids fingerprinting via exact timings.
fn duration_bucket(ms: u64) -> &'static str {
    match ms {
        0..=99 => "<100ms",
        100..=499 => "100-500ms",
        500..=1999 => "500ms-2s",
        2000..=9999 => "2-10s",
        _ => ">10s",
    }
}

/// The closed-enum event label from the command grammar.
fn event_label(command: &str, subcommand: Option<&str>) -> String {
    match subcommand {
        Some(s) => format!("{command}:{s}"),
        None => command.to_string(),
    }
}

/// Show the one-time first-run disclosure. Always writes the sentinel (so it is
/// genuinely one-time + never re-prompts non-interactively); prints the
/// paragraph only when analytics are enabled AND the session is interactive
/// human (D-05-13 non-interactive contract).
pub fn maybe_first_run_notice(output: &OutputConfig, enabled: bool) {
    let sentinel = saferskills_dir().join(NOTICE_SENTINEL);
    if sentinel.exists() {
        return;
    }
    // Best-effort sentinel write — never block a command on telemetry I/O.
    let _ = std::fs::create_dir_all(saferskills_dir());
    let _ = std::fs::write(&sentinel, b"shown\n");

    let interactive =
        enabled && !output.is_json() && !output.is_quiet() && std::io::stderr().is_terminal();
    if !interactive {
        return;
    }
    eprintln!(
        "SaferSkills collects anonymous usage analytics (which command ran, its exit code, and a\n\
         coarse duration — never arguments, names, paths, or any personal data) to improve the CLI.\n\
         Disable any time with SAFERSKILLS_NO_TELEMETRY=1 (DO_NOT_TRACK and CI are also honored).\n\
         Details: https://saferskills.ai/privacy\n"
    );
}

/// Emit the `command_invoked` event. A no-op unless analytics are enabled; the
/// network POST only happens under the `telemetry-network` feature and is
/// best-effort (a failure is swallowed — telemetry must never affect the user
/// command's outcome).
pub async fn capture_command_invoked(
    command: &str,
    subcommand: Option<&str>,
    exit_code: i32,
    duration_ms: u64,
    enabled: bool,
) {
    if !enabled {
        return;
    }
    let payload = serde_json::json!({
        "api_key": baked_key(),
        "event": "command_invoked",
        "properties": {
            "distinct_id": "saferskills-cli",
            "$process_person_profile": false,
            "command": event_label(command, subcommand),
            "exit_code": exit_code,
            "duration_bucket": duration_bucket(duration_ms),
            "cli_version": env!("CARGO_PKG_VERSION"),
        }
    });

    send(payload).await;
}

#[cfg(feature = "telemetry-network")]
async fn send(payload: serde_json::Value) {
    // Best-effort, tightly bounded — a network blip must not delay the command.
    let Ok(client) = reqwest::Client::builder()
        .use_rustls_tls()
        .timeout(std::time::Duration::from_millis(1500))
        .build()
    else {
        return;
    };
    let url = format!("{POSTHOG_HOST}/capture/");
    let _ = client.post(url).json(&payload).send().await;
}

#[cfg(not(feature = "telemetry-network"))]
async fn send(payload: serde_json::Value) {
    // Network path compiled out — the event is computed (for parity) but never
    // leaves the process.
    let _ = payload;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn disabled_short_circuits_regardless_of_env() {
        // config_allows = false ⇒ always disabled, independent of env/key.
        assert!(!is_enabled(false));
    }

    #[test]
    fn no_baked_key_means_disabled() {
        // In dev/test builds no key is baked, so analytics can never be on even
        // when config allows + no opt-out.
        if baked_key().is_empty() {
            // Mirrors the production guard: enabled requires a baked key.
            assert!(!is_enabled(true) || opted_out_env());
        }
    }

    #[test]
    fn duration_buckets() {
        assert_eq!(duration_bucket(0), "<100ms");
        assert_eq!(duration_bucket(250), "100-500ms");
        assert_eq!(duration_bucket(1500), "500ms-2s");
        assert_eq!(duration_bucket(5000), "2-10s");
        assert_eq!(duration_bucket(60_000), ">10s");
    }

    #[test]
    fn label_uses_grammar_not_values() {
        assert_eq!(event_label("info", None), "info");
        assert_eq!(event_label("update", Some("all")), "update:all");
    }
}
