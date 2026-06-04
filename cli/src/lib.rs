//! SaferSkills CLI — library root.
//!
//! The binary (`src/main.rs`) is a thin shell over this library: it parses the
//! clap tree, resolves output config, dispatches to a `commands::run_*` fn, and
//! maps the result to a process exit code. Everything testable lives here.
//!
//! Module map (mirrors `openlatch-client` minus its daemon/hook/auth/cloud
//! subsystems, D-05-03):
//! - [`cli`] — clap tree, global flags, [`cli::output`] / [`cli::color`] /
//!   [`cli::header`].
//! - [`core`] — [`core::config`], [`core::error`], [`core::http`],
//!   [`core::registry`], [`core::telemetry`].
//! - [`api`] — typed endpoint wrappers + [`api::dto`] wire types.
//! - [`commands`] — one handler per command.

pub mod api;
pub mod cli;
pub mod commands;
pub mod core;

// Flat re-exports so call sites can use `crate::config`, `crate::error`, … —
// the same ergonomic shape openlatch-client exposes.
pub use core::{config, error, http, registry, telemetry};
