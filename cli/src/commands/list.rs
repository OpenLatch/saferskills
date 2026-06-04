//! `saferskills list` — wired in Phase B.

use crate::cli::output::OutputConfig;
use crate::cli::ListArgs;
use crate::commands::not_implemented;
use crate::core::error::SsError;

/// Stub until Phase B.
pub async fn run_list(_args: &ListArgs, _output: &OutputConfig) -> Result<(), SsError> {
    Err(not_implemented("list", "Phase B"))
}
