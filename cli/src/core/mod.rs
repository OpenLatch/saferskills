//! Shared leaf modules: config + local state, the error model, the HTTP client,
//! the install registry, the rules-content cache, and telemetry.

pub mod config;
pub mod error;
pub mod http;
pub mod registry;
pub mod rules_content;
pub mod telemetry;
