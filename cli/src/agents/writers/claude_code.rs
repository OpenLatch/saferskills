//! Claude Code writer — HIGH confidence.
//!
//! Landmines (design.md §4): MCP key `mcpServers` in `~/.claude.json` (global) /
//! `.mcp.json` (project, repo root) — NOT `settings.json`. URL transport uses
//! `url`. (The `projects."<abs>".mcpServers` local-scope nesting is NOT used —
//! both our scopes write top-level `mcpServers`, see SCHEMAS.md.) Skills →
//! `~/.claude/skills/<name>/` (global) / `.claude/skills/<name>/` (project).
//! Source: code.claude.com/docs/en/mcp + /skills (2026-06-04).

use super::{Confidence, ConfigWriter, JsonMcpWriter, KeyShape};
use crate::agents::AgentId;

pub fn writer() -> Box<dyn ConfigWriter> {
    Box::new(JsonMcpWriter {
        id: AgentId::ClaudeCode,
        confidence: Confidence::High,
        key: KeyShape::Fixed(&["mcpServers"]),
        url_field: "url",
        supports_project: true,
        rules_ext: "",
    })
}
