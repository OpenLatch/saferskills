//! Command handlers. Dispatch is a single `match` in `main.rs` over the clap
//! enum → one free `run_*` fn per command (no command trait), per D-05-03.
//!
//! Phase A wired `info`, `completion`, and `man`; Phase B fills in the lifecycle
//! commands (`install` / `uninstall` / `update` / `list` / `doctor`). `scan`
//! remains a Phase-C stub returning `SS-E-1090`.

pub mod completion;
pub mod doctor;
pub mod info;
pub mod install;
pub mod list;
pub mod scan;
pub mod uninstall;
pub mod update;

use crate::core::error::{SsError, ERR_NOT_IMPLEMENTED};

/// Shared stub error for commands that land in a later phase.
pub(crate) fn not_implemented(command: &str, phase: &str) -> SsError {
    SsError::new(
        ERR_NOT_IMPLEMENTED,
        format!("`saferskills {command}` is not available in this build yet."),
    )
    .with_suggestion(format!("This command ships in {phase}."))
    .with_docs("https://saferskills.ai/docs/cli")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cli::output::{OutputConfig, OutputFormat};
    use crate::cli::ScanArgs;
    use crate::core::error::ERR_NOT_IMPLEMENTED;

    fn out() -> OutputConfig {
        OutputConfig {
            format: OutputFormat::Json, // suppress human output during the test
            verbose: false,
            quiet: true,
            color: false,
        }
    }

    #[test]
    fn not_implemented_carries_code_and_help() {
        let err = not_implemented("scan", "Phase C");
        assert_eq!(err.code, ERR_NOT_IMPLEMENTED);
        assert!(err.suggestion.unwrap().contains("Phase C"));
    }

    #[tokio::test]
    async fn scan_is_still_a_phase_c_stub() {
        let o = out();
        let err = scan::run_scan(
            &ScanArgs {
                target: None,
                local: false,
                private: false,
            },
            &o,
        )
        .await
        .unwrap_err();
        assert_eq!(err.code, ERR_NOT_IMPLEMENTED);
    }
}
