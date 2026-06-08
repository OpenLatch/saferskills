//! Anonymous telemetry — mirrors openlatch-client.
//!
//! Two channels, **exactly one prompt**:
//! - **Usage analytics** (the PostHog `command_invoked` event, here): opt-in.
//!   A single first-run question ([`resolve_telemetry_consent`]) stores the
//!   answer in the `telemetry` config key; OFF until accepted.
//! - **Install reporting** (the `/installs` API call in `commands::install`):
//!   **no consent** — it reports an anonymous `(agent, capability kind)` install
//!   count on every install ([`install_reporting_allowed`]). It is suppressed
//!   ONLY by a universal kill-switch (`CI` / `DO_NOT_TRACK` /
//!   `SAFERSKILLS_NO_TELEMETRY`) or a build with no baked key.
//!
//! The two share the same universal kill-switches and the same "source builds
//! send nothing" guarantee, so a single opt-out env silences both.
//!
//! - The PostHog project key is **baked at build time** by `build.rs`
//!   (`SAFERSKILLS_POSTHOG_KEY`). Empty (dev / forks) ⇒ a hard no-op: neither
//!   channel ever sends and the usage-analytics prompt is skipped entirely
//!   (source builds send nothing).
//! - **First-run consent (usage analytics only)**: on the first interactive
//!   launch the user is asked once whether to enable usage analytics; the answer
//!   is stored in `config.toml` and never re-asked. Any non-interactive context
//!   (`--json` / `--quiet` / `--non-interactive` / non-TTY / CI) — or a build
//!   with no baked key — stays OFF and never prompts (opt-in default).
//! - A single `command_invoked` event carries a CLOSED-ENUM `(command,
//!   subcommand)` label derived from the grammar — NEVER a flag value — plus
//!   the exit code and a coarse duration bucket. No PII, ever.
//! - Every event is tagged `product = "saferskills"` so the shared
//!   OpenLatch-portfolio PostHog project (one project for cost — D-19's
//!   separate-project rule superseded 2026-06-04) can filter SaferSkills data
//!   apart. PostHog is internal analytics; public brand independence is intact.
//! - Universal opt-out: `SAFERSKILLS_NO_TELEMETRY` / `DO_NOT_TRACK` / `CI`
//!   (any non-empty value) silences BOTH channels; `telemetry = false`
//!   additionally disables usage analytics. An explicit `SAFERSKILLS_TELEMETRY=1`
//!   forces usage analytics on without prompting.
//! - The network POST is gated behind the `telemetry-network` feature (a blip
//!   must never delay or fail a user command; the send is best-effort with a
//!   tight timeout).

use std::io::IsTerminal;

use crate::cli::output::OutputConfig;
use crate::core::config::{set_telemetry, Config};

/// The PostHog project key baked by `build.rs` (empty when unset).
pub const fn baked_key() -> &'static str {
    env!("SAFERSKILLS_POSTHOG_KEY")
}

/// The PostHog host baked by `build.rs`. Only referenced by the gated network
/// send path, so it is compiled in only under the `telemetry-network` feature.
#[cfg(feature = "telemetry-network")]
const POSTHOG_HOST: &str = env!("SAFERSKILLS_POSTHOG_HOST");

fn env_present(key: &str) -> bool {
    std::env::var_os(key).is_some_and(|v| !v.is_empty())
}

fn env_bool(key: &str) -> Option<bool> {
    std::env::var(key)
        .ok()
        .map(|v| matches!(v.as_str(), "true" | "1"))
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

/// Pure consent precedence: a universal opt-out forces OFF; else an explicit
/// `SAFERSKILLS_TELEMETRY` env wins; else the stored config key. `None` means
/// "not yet decided" — the caller prompts (interactive) or defaults off.
fn consent_from(opted_out: bool, env_explicit: Option<bool>, stored: Option<bool>) -> Option<bool> {
    if opted_out {
        return Some(false);
    }
    env_explicit.or(stored)
}

/// Resolve usage-analytics consent (the PostHog channel only — install reporting
/// is unconditional, see [`install_reporting_allowed`]), prompting **once** on
/// the first interactive launch and persisting the answer to `config.toml`.
///
/// Precedence: a universal opt-out env (`CI` / `DO_NOT_TRACK` /
/// `SAFERSKILLS_NO_TELEMETRY`) forces OFF; then an explicit `SAFERSKILLS_TELEMETRY`
/// env; then the stored `telemetry` config key. If still undecided: any
/// non-interactive context (`--json` / `--quiet` / `--non-interactive` / non-TTY /
/// CI) — or a build with no baked PostHog key (analytics can never send) — stays
/// OFF and never prompts; only an interactive TTY asks, and the choice is saved so
/// it is asked exactly once.
pub fn resolve_telemetry_consent(
    output: &OutputConfig,
    config: &Config,
    non_interactive: bool,
) -> bool {
    if let Some(v) = consent_from(
        opted_out_env(),
        env_bool("SAFERSKILLS_TELEMETRY"),
        config.telemetry,
    ) {
        return v;
    }
    let interactive = !non_interactive
        && !output.is_json()
        && !output.is_quiet()
        && std::io::stderr().is_terminal();
    // No baked key ⇒ analytics can never be sent, so never bother the user.
    if !interactive || baked_key().is_empty() {
        return false;
    }
    let choice = inquire::Confirm::new(
        "Enable anonymous usage analytics to help improve the SaferSkills CLI?",
    )
    .with_default(false)
    .with_help_message("Anonymous: which command ran, its exit code, and a coarse duration — never arguments, names, paths, or any PII. Change anytime in ~/.saferskills/config.toml or with SAFERSKILLS_NO_TELEMETRY=1.")
    .prompt()
    .unwrap_or(false);
    // Persist so we ask exactly once (best-effort — applies this run regardless).
    let _ = set_telemetry(choice);
    choice
}

/// Whether the unconditional install report may send. Install reporting carries
/// **no separate consent** — it fires on every install EXCEPT under a universal
/// kill-switch (`CI` / `DO_NOT_TRACK` / `SAFERSKILLS_NO_TELEMETRY`) or in a build
/// with no baked key (source / fork builds send nothing). The reported data is
/// anonymous — `(agent, capability kind)` only, never names / paths / PII.
pub fn install_reporting_allowed() -> bool {
    !opted_out_env() && !baked_key().is_empty()
}

/// Build the `command_invoked` event payload. Extracted from the send path so
/// the shape — especially the `product` discriminator and the no-PII property
/// set — is unit-testable without touching the network.
fn command_invoked_payload(
    command: &str,
    subcommand: Option<&str>,
    exit_code: i32,
    duration_ms: u64,
) -> serde_json::Value {
    serde_json::json!({
        "api_key": baked_key(),
        "event": "command_invoked",
        "properties": {
            "distinct_id": "saferskills-cli",
            "$process_person_profile": false,
            // Discriminator for the shared OpenLatch-portfolio PostHog project
            // (one project for cost — D-19's separate-project rule superseded
            // 2026-06-04). Lets SaferSkills events be filtered apart from other
            // products' in the same project.
            "product": "saferskills",
            "command": event_label(command, subcommand),
            "exit_code": exit_code,
            "duration_bucket": duration_bucket(duration_ms),
            "cli_version": env!("CARGO_PKG_VERSION"),
        }
    })
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
    send(command_invoked_payload(
        command,
        subcommand,
        exit_code,
        duration_ms,
    ))
    .await;
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
    fn consent_precedence() {
        // Universal opt-out forces OFF even over a stored / explicit "true".
        assert_eq!(consent_from(true, Some(true), Some(true)), Some(false));
        // Explicit env wins over the stored config key.
        assert_eq!(consent_from(false, Some(true), Some(false)), Some(true));
        assert_eq!(consent_from(false, Some(false), Some(true)), Some(false));
        // No env → the stored choice decides.
        assert_eq!(consent_from(false, None, Some(true)), Some(true));
        assert_eq!(consent_from(false, None, Some(false)), Some(false));
        // Nothing decided yet → caller must prompt / default off.
        assert_eq!(consent_from(false, None, None), None);
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

    #[test]
    fn payload_tags_product_and_carries_no_pii() {
        let p = command_invoked_payload("update", Some("all"), 0, 50);
        assert_eq!(p["event"], "command_invoked");
        // Discriminator for the shared PostHog project.
        assert_eq!(p["properties"]["product"], "saferskills");
        // Closed-enum grammar label, never a flag value.
        assert_eq!(p["properties"]["command"], "update:all");
        assert_eq!(p["properties"]["exit_code"], 0);
        assert_eq!(p["properties"]["duration_bucket"], "<100ms");
        // Person profiles stay off — no identity stitching.
        assert_eq!(p["properties"]["$process_person_profile"], false);
    }
}
