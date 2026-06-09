//! First-launch security audit (D-05-26).
//!
//! On the CLI's first interactive run, offer a one-time opt-in audit of
//! everything already installed across the user's agents. On accept it runs
//! `scan --local` once (public by default, with a private/unlisted option). The
//! choice is persisted (`config.toml::audited`) so it never re-prompts.
//!
//! **Fail-open**: any error here is swallowed — the audit must never change the
//! exit code of the user's actual command.

use std::io::IsTerminal;

use crate::cli::output::OutputConfig;
use crate::cli::{Interaction, ScanArgs};
use crate::commands::scan;
use crate::core::config::{set_audited, Config};
use crate::core::error::SsError;
use crate::core::registry;

/// What the first-run gate decides to do — pure, so it is unit-testable apart
/// from the prompt + scan I/O.
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum AuditAction {
    /// Already audited, or non-interactive — do nothing.
    NoOp,
    /// First run but nothing installed — silently mark audited, don't prompt.
    PersistOnly,
    /// First interactive run with installs — prompt.
    Prompt,
}

/// Decide the first-run action from the three inputs (no I/O).
pub(crate) fn decide(
    audited: Option<bool>,
    interactive: bool,
    registry_empty: bool,
) -> AuditAction {
    if audited == Some(true) {
        return AuditAction::NoOp;
    }
    if !interactive {
        return AuditAction::NoOp;
    }
    if registry_empty {
        return AuditAction::PersistOnly;
    }
    AuditAction::Prompt
}

/// Run the first-launch audit gate. Never returns an error — a failure is
/// swallowed so the user's actual command runs unaffected.
pub async fn maybe_first_run_audit(inter: Interaction, output: &OutputConfig) {
    let _ = try_first_run_audit(inter, output).await;
}

async fn try_first_run_audit(inter: Interaction, output: &OutputConfig) -> Result<(), SsError> {
    let config = Config::load()?;
    let interactive = !inter.non_interactive
        && !output.is_json()
        && !output.is_quiet()
        && std::io::stderr().is_terminal();
    let registry_empty = registry::load().map(|r| r.is_empty()).unwrap_or(true);

    match decide(config.audited, interactive, registry_empty) {
        AuditAction::NoOp => Ok(()),
        AuditAction::PersistOnly => {
            let _ = set_audited(true);
            Ok(())
        }
        AuditAction::Prompt => {
            let choice = inquire::Select::new(
                "First run: audit everything already installed across your agents?",
                vec![
                    "Yes — public report",
                    "Yes — private (unlisted) report",
                    "Skip",
                ],
            )
            .prompt()
            .unwrap_or("Skip");

            // Persist BEFORE running so a crash mid-scan never re-prompts.
            let _ = set_audited(true);

            let private = match choice {
                "Yes — public report" => Some(false),
                "Yes — private (unlisted) report" => Some(true),
                _ => None,
            };
            if let Some(private) = private {
                // Direct call (no dispatch recursion). Fail-open — ignore errors.
                let _ = scan::run_scan(
                    &ScanArgs {
                        target: None,
                        local: true,
                        private,
                        detailed: false,
                        agent: None,
                        fail_on: None,
                        baseline: None,
                        no_telemetry: false,
                        print_skill: false,
                        submit_blob: None,
                    },
                    output,
                )
                .await;
            }
            Ok(())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn already_audited_is_noop() {
        assert_eq!(decide(Some(true), true, false), AuditAction::NoOp);
        // Even interactive + installs present: a true flag short-circuits.
        assert_eq!(decide(Some(true), true, true), AuditAction::NoOp);
    }

    #[test]
    fn non_interactive_is_noop() {
        assert_eq!(decide(None, false, false), AuditAction::NoOp);
        assert_eq!(decide(Some(false), false, false), AuditAction::NoOp);
    }

    #[test]
    fn empty_registry_persists_without_prompt() {
        assert_eq!(decide(None, true, true), AuditAction::PersistOnly);
    }

    #[test]
    fn first_interactive_run_with_installs_prompts() {
        assert_eq!(decide(None, true, false), AuditAction::Prompt);
        assert_eq!(decide(Some(false), true, false), AuditAction::Prompt);
    }
}
