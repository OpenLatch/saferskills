//! Cursor writer — HIGH confidence (MCP).
//!
//! Landmines (design.md §4): MCP key `mcpServers` in `~/.cursor/mcp.json`
//! (global) / `.cursor/mcp.json` (project). URL transport uses `url`. Cursor has
//! no native Skills concept (it uses Rules `.cursor/rules/*.mdc`), so a skill
//! install surfaces a copy-paste fallback — but a skill is never offered for
//! Cursor anyway (backend agent_compat: skill → claude-code + openclaw only).
//! Source: cursor.com/docs/mcp + /rules (2026-06-04).

use super::{Confidence, ConfigWriter, JsonMcpWriter, KeyShape};
use crate::agents::AgentId;

pub fn writer() -> Box<dyn ConfigWriter> {
    Box::new(JsonMcpWriter {
        id: AgentId::Cursor,
        confidence: Confidence::High,
        key: KeyShape::Fixed(&["mcpServers"]),
        url_field: "url",
        supports_project: true,
        rules_ext: ".mdc",
    })
}
