//! Codex writer — HIGH confidence. The only TOML agent.
//!
//! Landmines (design.md §4): MCP entry is a TOML table `[mcp_servers.<name>]` in
//! `~/.codex/config.toml` (global) / `.codex/config.toml` (project) — written
//! format-preservingly via `toml_edit`. HTTP transport uses `url` +
//! `bearer_token_env_var`. Codex Desktop has been observed to rewrite/drop MCP
//! entries on a Windows restart, so `doctor`'s verify re-reads the file.
//! Skills → `~/.codex/skills/<name>/` (+ `openai.yaml`).
//! Source: developers.openai.com/codex/mcp + /skills + /config-reference.

use super::{CodexWriter, Confidence, ConfigWriter};

pub fn writer() -> Box<dyn ConfigWriter> {
    Box::new(CodexWriter {
        confidence: Confidence::High,
    })
}
