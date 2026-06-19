//! Cline writer — HIGH confidence (MCP). Native-skill surface is MED (Cline has
//! no native skill concept, so a skill is never written here — see SCHEMAS.md).
//!
//! Config-schema landmines: MCP key `mcpServers` in the VS Code globalStorage
//! `…/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` (the VS Code
//! variant — `Code` / `Code - Insiders` / `VSCodium` — is resolved at detection
//! time), or the CLI's `~/.cline/mcp.json`. Entries may also carry
//! `disabled`/`autoApprove` keys, which our additive merge leaves untouched on
//! sibling servers. URL transport uses `url`. Global-only.
//! Source: docs.cline.bot/mcp/configuring-mcp-servers (2026-06-04).

use super::{Confidence, ConfigWriter, JsonMcpWriter, KeyShape};
use crate::agents::AgentId;

pub fn writer() -> Box<dyn ConfigWriter> {
    Box::new(JsonMcpWriter {
        id: AgentId::Cline,
        confidence: Confidence::High,
        key: KeyShape::Fixed(&["mcpServers"]),
        url_field: "url",
        supports_project: false,
        rules_ext: ".md",
    })
}
