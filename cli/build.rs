// Build script for the SaferSkills CLI.
//
// Scope (D-05-08, D-05-13): this build script does EXACTLY ONE thing — bake the
// PostHog project key into the binary as a compile-time constant. There is NO
// wire-type codegen here. The CLI's wire DTOs are hand-written in
// `src/api/dto.rs` and guarded by a contract test against `services/api/
// openapi.json` (the CLI is an API consumer, not part of the repo's
// 8-generator schema pipeline), so typify/schemars/syn/prettyplease are
// deliberately absent from `[build-dependencies]`.
//
// Production: CI sets `SAFERSKILLS_POSTHOG_KEY` from a secret on the release
// build. Developers / forks: leave it unset — the baked constant is then empty
// and the telemetry subsystem is a hard no-op (D-05-13, invariant: zero
// network without a key).

fn main() {
    println!("cargo:rerun-if-env-changed=SAFERSKILLS_POSTHOG_KEY");
    let key = std::env::var("SAFERSKILLS_POSTHOG_KEY").unwrap_or_default();
    println!("cargo:rustc-env=SAFERSKILLS_POSTHOG_KEY={key}");

    println!("cargo:rerun-if-env-changed=SAFERSKILLS_POSTHOG_HOST");
    let host = std::env::var("SAFERSKILLS_POSTHOG_HOST")
        .unwrap_or_else(|_| "https://eu.i.posthog.com".to_string());
    println!("cargo:rustc-env=SAFERSKILLS_POSTHOG_HOST={host}");

    // Sentry DSN baking (crash reporting). Mirrors the PostHog key pattern —
    // unset at build time → empty string → the crash_report module
    // short-circuits to a no-op guard (the same "no baked key ⇒ silent no-op"
    // discipline as telemetry). See src/core/crash_report/.
    //
    // Production: CI sets `SAFERSKILLS_SENTRY_DSN` from a secret on the release
    // build. Developers / forks: leave it unset — crash reporting is then inert.
    println!("cargo:rerun-if-env-changed=SAFERSKILLS_SENTRY_DSN");
    let dsn = std::env::var("SAFERSKILLS_SENTRY_DSN").unwrap_or_default();
    println!("cargo:rustc-env=SAFERSKILLS_SENTRY_DSN={dsn}");

    // Release identifier for the Sentry `release` field
    // (`saferskills-cli@<release>`). Priority:
    //   GITHUB_SHA → SAFERSKILLS_RELEASE → `git rev-parse HEAD` → CARGO_PKG_VERSION.
    // The CARGO_PKG_VERSION fallback covers `cargo install` from crates.io where
    // there is no .git directory.
    println!("cargo:rerun-if-env-changed=GITHUB_SHA");
    println!("cargo:rerun-if-env-changed=SAFERSKILLS_RELEASE");
    let release = resolve_release();
    println!("cargo:rustc-env=SAFERSKILLS_RELEASE={release}");
}

/// Resolve the release identifier Sentry uses as the `release` field. See the
/// priority list at the call site.
fn resolve_release() -> String {
    if let Ok(sha) = std::env::var("GITHUB_SHA") {
        if !sha.is_empty() {
            return sha;
        }
    }
    if let Ok(rel) = std::env::var("SAFERSKILLS_RELEASE") {
        if !rel.is_empty() {
            return rel;
        }
    }
    if let Ok(output) = std::process::Command::new("git")
        .args(["rev-parse", "HEAD"])
        .output()
    {
        if output.status.success() {
            if let Ok(s) = String::from_utf8(output.stdout) {
                let trimmed = s.trim();
                if !trimmed.is_empty() {
                    return trimmed.to_string();
                }
            }
        }
    }
    format!("v{}", env!("CARGO_PKG_VERSION"))
}
