//! `saferskills uninstall` — wired in Phase B.

use crate::cli::output::OutputConfig;
use crate::cli::UninstallArgs;
use crate::commands::not_implemented;
use crate::core::error::SsError;

/// Stub until Phase B.
pub async fn run_uninstall(_args: &UninstallArgs, _output: &OutputConfig) -> Result<(), SsError> {
    Err(not_implemented("uninstall", "Phase B"))
}
