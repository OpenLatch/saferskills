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
}
