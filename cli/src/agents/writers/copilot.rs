//! GitHub Copilot writer — HIGH confidence.
//!
//! Config-schema landmines: **two surfaces with different keys.** The CLI
//! surface (`~/.copilot/mcp-config.json`) uses `mcpServers` (`type:"local"`);
//! the VS Code surface (`.vscode/mcp.json`, project scope) uses **`servers`**
//! (NOT `mcpServers`). [`KeyShape::CopilotSurface`] picks the key from the
//! resolved path. URL transport uses `url`. Skills → `~/.copilot/skills/`,
//! `.github/skills/`. Source: code.visualstudio.com/docs/agent-customization/
//! mcp-servers + docs.github.com copilot-cli (2026-06-04).

use super::{Confidence, ConfigWriter, JsonMcpWriter, KeyShape};
use crate::agents::AgentId;

pub fn writer() -> Box<dyn ConfigWriter> {
    Box::new(JsonMcpWriter {
        id: AgentId::Copilot,
        confidence: Confidence::High,
        key: KeyShape::CopilotSurface,
        url_field: "url",
        supports_project: true,
        rules_ext: ".instructions.md",
    })
}
