//! Command handlers. Dispatch is a single `match` in `main.rs` over the clap
//! enum → one free `run_*` fn per command (no command trait).

pub mod agent;
pub mod audit;
pub mod capability;
pub mod completion;
pub mod doctor;
pub mod info;
pub mod install;
pub mod list;
pub(crate) mod report;
pub mod search;
pub mod uninstall;
pub mod update;

#[cfg(test)]
mod tests {
    use super::capability;
    use crate::cli::output::{OutputConfig, OutputFormat};
    use crate::cli::CapabilityArgs;
    use crate::core::error::ERR_SCAN_TARGET;

    fn out() -> OutputConfig {
        OutputConfig {
            format: OutputFormat::Json, // suppress human output during the test
            verbose: false,
            quiet: true,
            color: false,
        }
    }

    // A non-existent path target fails fast with a target error before any
    // network. (No target → a local audit instead; covered in tests/smoke.rs.)
    #[tokio::test]
    async fn capability_nonexistent_path_is_a_target_error() {
        let o = out();
        let err = capability::run_capability(
            &CapabilityArgs {
                target: Some("./definitely-not-a-real-path-xyz".to_string()),
                to: vec![],
                private: false,
                detailed: false,
            },
            &o,
        )
        .await
        .unwrap_err();
        assert_eq!(err.code, ERR_SCAN_TARGET);
    }
}
