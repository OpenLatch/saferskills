//! `saferskills completion <shell>` + the hidden `man` generator (D-05-18,
//! design §7). Both write their artifact to **stdout** (it is machine data).

use std::io;

use clap::CommandFactory;

use crate::cli::output::OutputConfig;
use crate::cli::Cli;
use crate::core::error::{SsError, ERR_STATE_WRITE_FAILED};

/// Emit a shell completion script for `shell` to stdout.
pub fn run_completion(shell: clap_complete::Shell, _output: &OutputConfig) -> Result<(), SsError> {
    let mut cmd = Cli::command();
    clap_complete::generate(shell, &mut cmd, "saferskills", &mut io::stdout());
    Ok(())
}

/// Render the troff man page to stdout (consumed by packaging).
pub fn run_man(_output: &OutputConfig) -> Result<(), SsError> {
    let cmd = Cli::command();
    let man = clap_mangen::Man::new(cmd);
    man.render(&mut io::stdout()).map_err(|e| {
        SsError::new(
            ERR_STATE_WRITE_FAILED,
            format!("Failed to render man page: {e}"),
        )
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cli::output::OutputFormat;

    fn out() -> OutputConfig {
        OutputConfig {
            format: OutputFormat::Human,
            verbose: false,
            quiet: false,
            color: false,
        }
    }

    #[test]
    fn completion_generates_for_each_shell() {
        for shell in [
            clap_complete::Shell::Bash,
            clap_complete::Shell::Zsh,
            clap_complete::Shell::Fish,
            clap_complete::Shell::PowerShell,
        ] {
            run_completion(shell, &out()).unwrap();
        }
    }

    #[test]
    fn man_renders() {
        run_man(&out()).unwrap();
    }
}
