//! Command handlers. Dispatch is a single `match` in `main.rs` over the clap
//! enum → one free `run_*` fn per command (no command trait), per D-05-03.
//!
//! Phase A wires `info`, `completion`, and `man`. The lifecycle commands
//! (`install` / `uninstall` / `update` / `list` / `doctor`) and `scan` are
//! present so the binary is whole + `--help` shows the full surface, but return
//! `SS-E-1090` until Phase B/C fill them in.

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
    use crate::cli::{DoctorArgs, InstallArgs, ListArgs, ScanArgs, UninstallArgs, UpdateArgs};
    use crate::core::error::ERR_NOT_IMPLEMENTED;

    fn out() -> OutputConfig {
        OutputConfig {
            format: OutputFormat::Human,
            verbose: false,
            quiet: false,
            color: false,
        }
    }

    #[test]
    fn not_implemented_carries_code_and_help() {
        let err = not_implemented("install", "Phase B");
        assert_eq!(err.code, ERR_NOT_IMPLEMENTED);
        assert!(err.suggestion.unwrap().contains("Phase B"));
    }

    #[tokio::test]
    async fn every_stub_returns_not_implemented() {
        let o = out();
        let install = InstallArgs {
            name: "x".into(),
            to: vec![],
            all: false,
            project: false,
            update: false,
            reinstall: false,
            seen_score: None,
            dry_run: false,
        };
        assert!(install::run_install(&install, &o).await.is_err());
        assert!(
            uninstall::run_uninstall(&UninstallArgs { name: "x".into() }, &o)
                .await
                .is_err()
        );
        assert!(update::run_update(
            &UpdateArgs {
                name: None,
                all: false,
                prune_red: false
            },
            &o
        )
        .await
        .is_err());
        assert!(list::run_list(&ListArgs {}, &o).await.is_err());
        assert!(scan::run_scan(
            &ScanArgs {
                target: None,
                local: false,
                private: false
            },
            &o
        )
        .await
        .is_err());
        assert!(doctor::run_doctor(&DoctorArgs {}, &o).await.is_err());
    }
}
