//! Gemini writer — HIGH confidence (MCP); skill-dir surface is MED (not written
//! by this CLI — backend agent_compat keeps skills off Gemini; see SCHEMAS.md).
//!
//! Config-schema landmines: MCP key `mcpServers` in `~/.gemini/settings.json`
//! (global) / `.gemini/settings.json` (project) — distinct from the sibling
//! `mcp` object. URL transport uses `url` (SSE) or `httpUrl` (HTTP); we default
//! the remap to `url`. Source: github.com/google-gemini/gemini-cli docs/tools/
//! mcp-server.md (2026-06-04).

use super::{Confidence, ConfigWriter, JsonMcpWriter, KeyShape};
use crate::agents::AgentId;

pub fn writer() -> Box<dyn ConfigWriter> {
    Box::new(JsonMcpWriter {
        id: AgentId::Gemini,
        confidence: Confidence::High,
        key: KeyShape::Fixed(&["mcpServers"]),
        url_field: "url",
        supports_project: true,
        rules_ext: "",
    })
}
