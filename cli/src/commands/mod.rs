//! Command handlers. Dispatch is a single `match` in `main.rs` over the clap
//! enum → one free `run_*` fn per command (no command trait), per D-05-03.
//!
//! Phase A wired `info`, `completion`, and `man`; Phase B fills in the lifecycle
//! commands (`install` / `uninstall` / `update` / `list` / `doctor`); Phase C
//! ships `scan` / `scan --local` + the first-launch `audit` gate.

pub mod audit;
pub mod completion;
pub mod doctor;
pub mod info;
pub mod install;
pub mod list;
pub mod scan;
pub mod uninstall;
pub mod update;

#[cfg(test)]
mod tests {
    use super::scan;
    use crate::cli::output::{OutputConfig, OutputFormat};
    use crate::cli::ScanArgs;
    use crate::core::error::ERR_SCAN_TARGET;

    fn out() -> OutputConfig {
        OutputConfig {
            format: OutputFormat::Json, // suppress human output during the test
            verbose: false,
            quiet: true,
            color: false,
        }
    }

    #[tokio::test]
    async fn scan_without_target_is_a_target_error() {
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
        assert_eq!(err.code, ERR_SCAN_TARGET);
    }
}
