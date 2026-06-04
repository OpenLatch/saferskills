//! Shared leaf modules: config + local state, the error model, the HTTP client,
//! the install registry, the Proof-of-Work solver, and telemetry.

pub mod config;
pub mod error;
pub mod http;
pub mod pow;
pub mod registry;
pub mod telemetry;
