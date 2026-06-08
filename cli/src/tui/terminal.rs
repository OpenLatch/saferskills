//! Terminal lifecycle for the `search` TUI — RAII setup/teardown + a signal
//! backstop.
//!
//! The TUI runs in the raw-mode alternate screen on **stderr** (stdout stays
//! reserved for machine output). [`TerminalGuard`] owns that state: construction
//! enables raw mode + enters the alt screen; `Drop` reverses both. Because the
//! release profile uses `panic = "unwind"` (see `cli/Cargo.toml`), the guard's
//! `Drop` also runs on a panic unwind, so a panic mid-TUI still restores the
//! terminal.
//!
//! The one path that skips `Drop` is `process::exit` from the global `ctrlc`
//! handler (`main.rs`) on an *external* SIGINT. [`restore_on_signal`] is the
//! backstop for exactly that: a best-effort raw-mode/alt-screen restore, gated by
//! the [`is_active`] flag so it is a hard no-op for every non-TUI command.

use std::io::{Stderr, Write};
use std::sync::atomic::{AtomicBool, Ordering};

use crossterm::terminal::{
    disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen,
};
use crossterm::ExecutableCommand;
use ratatui::backend::CrosstermBackend;
use ratatui::Terminal;

use crate::core::error::{SsError, ERR_BUG};

/// `true` while a [`TerminalGuard`] is live. Read by [`restore_on_signal`] so the
/// ctrlc backstop only touches the terminal when a TUI actually owns it.
static ACTIVE: AtomicBool = AtomicBool::new(false);

/// Whether a TUI currently owns the terminal (raw mode + alt screen).
pub fn is_active() -> bool {
    ACTIVE.load(Ordering::SeqCst)
}

/// Best-effort terminal restore for an external SIGINT that will `process::exit`
/// (skipping every `Drop`). A no-op unless a TUI is active. Errors are swallowed
/// — we are already on the way out and cannot do better than try.
///
/// Called from the global `ctrlc` handler in `main.rs` BEFORE `process::exit`.
pub fn restore_on_signal() {
    if !ACTIVE.swap(false, Ordering::SeqCst) {
        return;
    }
    let _ = disable_raw_mode();
    let _ = std::io::stderr().execute(LeaveAlternateScreen);
}

/// RAII guard owning the raw-mode alternate screen on stderr. Build with
/// [`TerminalGuard::enter`]; the ratatui [`Terminal`] is reached via
/// [`TerminalGuard::terminal`]. Dropping leaves the alt screen + disables raw
/// mode (also on a panic unwind).
pub struct TerminalGuard {
    terminal: Terminal<CrosstermBackend<Stderr>>,
}

impl TerminalGuard {
    /// Enter raw mode + the alternate screen on stderr and build the ratatui
    /// terminal. Sets the [`ACTIVE`] flag for [`restore_on_signal`].
    pub fn enter() -> Result<Self, SsError> {
        enable_raw_mode().map_err(term_err)?;
        let mut stderr = std::io::stderr();
        if let Err(e) = stderr.execute(EnterAlternateScreen) {
            // Roll back the raw-mode change so we don't leave the terminal half-set.
            let _ = disable_raw_mode();
            return Err(term_err(e));
        }
        let backend = CrosstermBackend::new(stderr);
        let terminal = Terminal::new(backend).map_err(|e| {
            let _ = std::io::stderr().execute(LeaveAlternateScreen);
            let _ = disable_raw_mode();
            term_err(e)
        })?;
        ACTIVE.store(true, Ordering::SeqCst);
        Ok(Self { terminal })
    }

    /// Mutable access to the underlying ratatui terminal (for `draw`).
    pub fn terminal(&mut self) -> &mut Terminal<CrosstermBackend<Stderr>> {
        &mut self.terminal
    }
}

impl Drop for TerminalGuard {
    fn drop(&mut self) {
        // Clear the active flag first so a concurrent signal handler no-ops.
        ACTIVE.store(false, Ordering::SeqCst);
        let _ = self.terminal.show_cursor();
        let _ = self.terminal.backend_mut().flush();
        let _ = std::io::stderr().execute(LeaveAlternateScreen);
        let _ = disable_raw_mode();
    }
}

fn term_err(e: std::io::Error) -> SsError {
    SsError::new(ERR_BUG, format!("Failed to set up the terminal UI: {e}"))
        .with_suggestion("Run in a real terminal, or use `saferskills search <query> --json`.")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn restore_on_signal_is_noop_when_inactive() {
        // No TUI active → the flag stays false and nothing is touched.
        ACTIVE.store(false, Ordering::SeqCst);
        restore_on_signal();
        assert!(!is_active());
    }
}
