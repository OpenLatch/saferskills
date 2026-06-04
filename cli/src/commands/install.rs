//! `saferskills install` — wired in Phase B (the 8 config writers + lifecycle).

use crate::cli::output::OutputConfig;
use crate::cli::InstallArgs;
use crate::commands::not_implemented;
use crate::core::error::SsError;

/// Stub until Phase B.
pub async fn run_install(_args: &InstallArgs, _output: &OutputConfig) -> Result<(), SsError> {
    Err(not_implemented("install", "Phase B"))
}
