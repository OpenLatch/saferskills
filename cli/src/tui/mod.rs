//! Interactive terminal UI for the `search` command (the only TUI surface).
//!
//! The TUI draws to **stderr** (the TTY) so stdout stays machine-clean, runs in
//! the raw-mode alternate screen behind a RAII [`terminal::TerminalGuard`], and
//! is a thin render layer over a pure state core ([`search::state`]). All the
//! ranking / facet / staleness logic is pure + unit-tested; the ratatui draw +
//! event loop stay minimal.

pub mod search;
pub mod terminal;
