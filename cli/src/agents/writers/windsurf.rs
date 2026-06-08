//! Windsurf writer — HIGH confidence (MCP); hooks surface is MED (not written
//! by this CLI — see SCHEMAS.md).
//!
//! Landmines (design.md §4): MCP key `mcpServers` in
//! `~/.codeium/windsurf/mcp_config.json` — **global only** (`--project` is
//! rejected). Remote transport uses **`serverUrl`** (NOT `url`). Needs an editor
//! restart to apply ("write succeeded" ≠ "active") — `doctor`'s verify re-reads
//! the file, which is the strongest check we can make headlessly.
//! Source: docs.windsurf.com/windsurf/cascade/mcp (2026-06-04).

use super::{Confidence, ConfigWriter, JsonMcpWriter, KeyShape};
use crate::agents::AgentId;

pub fn writer() -> Box<dyn ConfigWriter> {
    Box::new(JsonMcpWriter {
        id: AgentId::Windsurf,
        confidence: Confidence::High,
        key: KeyShape::Fixed(&["mcpServers"]),
        url_field: "serverUrl",
        supports_project: false,
        rules_ext: ".md",
    })
}
