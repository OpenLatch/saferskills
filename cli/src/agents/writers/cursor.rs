//! Cursor writer — HIGH confidence (MCP).
//!
//! Landmines (design.md §4): MCP key `mcpServers` in `~/.cursor/mcp.json`
//! (global) / `.cursor/mcp.json` (project). URL transport uses `url`. Cursor has
//! no native Skills concept (it uses Rules `.cursor/rules/*.mdc`), so a `kind:skill`
//! is rendered to a `.mdc` Agent-Requested rule by the shared skill renderer
//! (`writers::render`, plan 02) — backend `agent_compat` now lists skill for all
//! eight agents, so Cursor IS a skill target. Source: cursor.com/docs/mcp + /rules
//! (2026-06-04).

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
