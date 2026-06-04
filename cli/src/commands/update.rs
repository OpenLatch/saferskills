//! `saferskills update` / `update --all` — wired in Phase B.

use crate::cli::output::OutputConfig;
use crate::cli::UpdateArgs;
use crate::commands::not_implemented;
use crate::core::error::SsError;

/// Stub until Phase B.
pub async fn run_update(_args: &UpdateArgs, _output: &OutputConfig) -> Result<(), SsError> {
    Err(not_implemented("update", "Phase B"))
}
