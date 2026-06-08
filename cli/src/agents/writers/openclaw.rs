//! OpenClaw writer — MEDIUM confidence (key-shape is the volatile surface).
//!
//! Landmines (design.md §4): the MCP key shape is **ambiguous** — `mcpServers`
//! vs nested `mcp.servers`. Rather than shell out to `openclaw mcp add` (which
//! can't capture a precise prior for a byte-exact rollback and needs the binary
//! present), we hand-write JSON and **probe** the existing file for its shape
//! ([`KeyShape::Openclaw`]), defaulting to `mcpServers` for a fresh file. Config
//! `~/.openclaw/openclaw.json` (global) / `.mcp.json` (workspace). Needs a
//! gateway restart to apply. `doctor` flags this MED writer + PENDING live-verify
//! (SCHEMAS.md). Source: docs.openclaw.ai/cli/mcp (key-shape unverified).

use super::{Confidence, ConfigWriter, JsonMcpWriter, KeyShape};
use crate::agents::AgentId;

pub fn writer() -> Box<dyn ConfigWriter> {
    Box::new(JsonMcpWriter {
        id: AgentId::Openclaw,
        confidence: Confidence::Medium,
        key: KeyShape::Openclaw,
        url_field: "url",
        supports_project: true,
        rules_ext: "",
    })
}
