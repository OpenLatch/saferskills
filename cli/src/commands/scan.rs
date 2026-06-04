//! `saferskills scan` / `scan --local` — wired in Phase C (PoW submit path).

use crate::cli::output::OutputConfig;
use crate::cli::ScanArgs;
use crate::commands::not_implemented;
use crate::core::error::SsError;

/// Stub until Phase C.
pub async fn run_scan(_args: &ScanArgs, _output: &OutputConfig) -> Result<(), SsError> {
    Err(not_implemented("scan", "Phase C"))
}
