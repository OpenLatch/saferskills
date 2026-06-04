//! `saferskills doctor` — wired in Phase B (registry-vs-filesystem drift).

use crate::cli::output::OutputConfig;
use crate::cli::DoctorArgs;
use crate::commands::not_implemented;
use crate::core::error::SsError;

/// Stub until Phase B.
pub async fn run_doctor(_args: &DoctorArgs, _output: &OutputConfig) -> Result<(), SsError> {
    Err(not_implemented("doctor", "Phase B"))
}
