//! The eight per-agent config writers (D-05-15, D-05-16).
//!
//! Each agent module documents its config-key + URL-field landmines (the
//! load-bearing per-agent differences from design.md §4) and constructs a writer
//! over the shared engine in [`super::writer`]. Seven agents map-merge JSON via a
//! [`JsonMcpWriter`] parameterised by a [`KeyShape`]; Codex map-merges TOML via
//! [`CodexWriter`]. Pinned known-good schemas + the live-verification checklist
//! for the volatile writers live in `SCHEMAS.md`.

pub mod claude_code;
pub mod cline;
pub mod codex;
pub mod copilot;
pub mod cursor;
pub mod gemini;
pub mod openclaw;
pub mod windsurf;

use std::path::Path;

use serde_json::Value;

use super::writer::{
    install_skill, merge_json_mcp, merge_toml_mcp, openclaw_key, reject_project_if_unsupported,
    revert_changes, skill_supported, verify_json_mcp, verify_toml_mcp, Confidence, ConfigWriter,
    ResolvedItem, VerifyStatus,
};
use super::{AgentId, DetectedAgent};
use crate::core::error::{SsError, ERR_WRITER_UNSUPPORTED};
use crate::core::registry::InstallChange;

/// Resolve the writer for an agent id (used by the install lifecycle).
pub fn writer_for(id: AgentId) -> Box<dyn ConfigWriter> {
    match id {
        AgentId::ClaudeCode => claude_code::writer(),
        AgentId::Cursor => cursor::writer(),
        AgentId::Codex => codex::writer(),
        AgentId::Copilot => copilot::writer(),
        AgentId::Windsurf => windsurf::writer(),
        AgentId::Cline => cline::writer(),
        AgentId::Gemini => gemini::writer(),
        AgentId::Openclaw => openclaw::writer(),
    }
}

/// How an agent's MCP container key is resolved.
#[derive(Debug, Clone, Copy)]
pub enum KeyShape {
    /// A fixed key path, e.g. `["mcpServers"]`.
    Fixed(&'static [&'static str]),
    /// OpenClaw — probe the existing file for `mcpServers` vs nested `mcp.servers`.
    Openclaw,
    /// Copilot — `servers` on the VS Code surface (`.vscode/mcp.json`),
    /// `mcpServers` on the CLI surface (`~/.copilot/mcp-config.json`).
    CopilotSurface,
}

impl KeyShape {
    fn resolve(self, path: &Path) -> Vec<&'static str> {
        match self {
            KeyShape::Fixed(p) => p.to_vec(),
            KeyShape::Openclaw => openclaw_key(path),
            KeyShape::CopilotSurface => {
                let is_vscode = path.components().any(|c| c.as_os_str() == ".vscode");
                if is_vscode {
                    vec!["servers"]
                } else {
                    vec!["mcpServers"]
                }
            }
        }
    }
}

/// The generic JSON map-merge writer shared by every agent but Codex.
pub struct JsonMcpWriter {
    pub id: AgentId,
    pub confidence: Confidence,
    pub key: KeyShape,
    /// The URL field name for a remote/URL-transport MCP entry (landmine):
    /// `serverUrl` (Windsurf), `httpUrl`/`url` (Gemini), `url` (everyone else).
    pub url_field: &'static str,
    pub supports_project: bool,
}

/// Rename a generic `"url"` field to the agent's URL-field name (landmine). A
/// command-based entry (no `"url"`) passes through unchanged.
fn remap_url_field(entry: &Value, url_field: &str) -> Value {
    if url_field == "url" {
        return entry.clone();
    }
    if let Value::Object(map) = entry {
        if map.contains_key("url") && !map.contains_key(url_field) {
            let mut m = map.clone();
            if let Some(u) = m.remove("url") {
                m.insert(url_field.to_string(), u);
            }
            return Value::Object(m);
        }
    }
    entry.clone()
}

fn no_entry_err(id: AgentId) -> SsError {
    SsError::new(
        ERR_WRITER_UNSUPPORTED,
        format!("No MCP launch spec resolved for {}.", id.display_name()),
    )
}

fn no_skill_dir_err(id: AgentId) -> SsError {
    SsError::new(
        ERR_WRITER_UNSUPPORTED,
        format!(
            "{} has no skills directory for a skill install.",
            id.display_name()
        ),
    )
    .with_suggestion("This capability can't be auto-installed for this agent; copy it in manually.")
}

impl ConfigWriter for JsonMcpWriter {
    fn id(&self) -> AgentId {
        self.id
    }
    fn confidence(&self) -> Confidence {
        self.confidence
    }
    fn supports_kind(&self, kind: &str, agent: &DetectedAgent) -> bool {
        skill_supported(kind, agent)
    }

    fn install(
        &self,
        item: &ResolvedItem,
        agent: &DetectedAgent,
        dry_run: bool,
    ) -> Result<Vec<InstallChange>, SsError> {
        reject_project_if_unsupported(self.supports_project, agent)?;
        match item.kind.as_str() {
            "mcp_server" => {
                let entry = item
                    .mcp_entry
                    .as_ref()
                    .ok_or_else(|| no_entry_err(self.id))?;
                let entry = remap_url_field(entry, self.url_field);
                let path = &agent.mcp_config_path;
                let key = self.key.resolve(path);
                let change = merge_json_mcp(path, &key, &item.name, &entry, dry_run)?;
                Ok(vec![change])
            }
            "skill" => {
                let skill_dir = agent
                    .skill_dir
                    .as_ref()
                    .ok_or_else(|| no_skill_dir_err(self.id))?;
                let zip = item
                    .skill_zip
                    .as_ref()
                    .ok_or_else(|| no_entry_err(self.id))?;
                Ok(vec![install_skill(skill_dir, &item.name, zip, dry_run)?])
            }
            other => Err(SsError::new(
                ERR_WRITER_UNSUPPORTED,
                format!(
                    "{} cannot install a `{other}` capability.",
                    self.id.display_name()
                ),
            )),
        }
    }

    fn uninstall(&self, changes: &[InstallChange]) -> Result<(), SsError> {
        revert_changes(changes)
    }

    fn verify(&self, item: &ResolvedItem, agent: &DetectedAgent) -> VerifyStatus {
        match item.kind.as_str() {
            "mcp_server" => {
                let key = self.key.resolve(&agent.mcp_config_path);
                verify_json_mcp(&agent.mcp_config_path, &key, &item.name)
            }
            "skill" => match agent.skill_dir.as_ref() {
                Some(dir) if dir.join(&item.name).exists() => VerifyStatus::Ok,
                _ => VerifyStatus::Missing,
            },
            _ => VerifyStatus::Missing,
        }
    }
}

/// Codex map-merges TOML (`[mcp_servers.<name>]`) — its own writer.
pub struct CodexWriter {
    pub confidence: Confidence,
}

impl ConfigWriter for CodexWriter {
    fn id(&self) -> AgentId {
        AgentId::Codex
    }
    fn confidence(&self) -> Confidence {
        self.confidence
    }
    fn supports_kind(&self, kind: &str, agent: &DetectedAgent) -> bool {
        skill_supported(kind, agent)
    }

    fn install(
        &self,
        item: &ResolvedItem,
        agent: &DetectedAgent,
        dry_run: bool,
    ) -> Result<Vec<InstallChange>, SsError> {
        match item.kind.as_str() {
            "mcp_server" => {
                let entry = item
                    .mcp_entry
                    .as_ref()
                    .ok_or_else(|| no_entry_err(AgentId::Codex))?;
                Ok(vec![merge_toml_mcp(
                    &agent.mcp_config_path,
                    &item.name,
                    entry,
                    dry_run,
                )?])
            }
            "skill" => {
                let skill_dir = agent
                    .skill_dir
                    .as_ref()
                    .ok_or_else(|| no_skill_dir_err(AgentId::Codex))?;
                let zip = item
                    .skill_zip
                    .as_ref()
                    .ok_or_else(|| no_entry_err(AgentId::Codex))?;
                Ok(vec![install_skill(skill_dir, &item.name, zip, dry_run)?])
            }
            other => Err(SsError::new(
                ERR_WRITER_UNSUPPORTED,
                format!("Codex cannot install a `{other}` capability."),
            )),
        }
    }

    fn uninstall(&self, changes: &[InstallChange]) -> Result<(), SsError> {
        revert_changes(changes)
    }

    fn verify(&self, item: &ResolvedItem, agent: &DetectedAgent) -> VerifyStatus {
        match item.kind.as_str() {
            "mcp_server" => verify_toml_mcp(&agent.mcp_config_path, &item.name),
            "skill" => match agent.skill_dir.as_ref() {
                Some(dir) if dir.join(&item.name).exists() => VerifyStatus::Ok,
                _ => VerifyStatus::Missing,
            },
            _ => VerifyStatus::Missing,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn writer_for_every_agent() {
        for id in super::super::ALL_AGENTS {
            let w = writer_for(id);
            assert_eq!(w.id(), id);
        }
    }

    #[test]
    fn copilot_surface_picks_servers_for_vscode() {
        assert_eq!(
            KeyShape::CopilotSurface.resolve(Path::new("/repo/.vscode/mcp.json")),
            vec!["servers"]
        );
        assert_eq!(
            KeyShape::CopilotSurface.resolve(Path::new("/home/u/.copilot/mcp-config.json")),
            vec!["mcpServers"]
        );
    }

    #[test]
    fn url_field_remap_renames_only_url_entries() {
        let url_entry = serde_json::json!({"url": "https://x"});
        let out = remap_url_field(&url_entry, "serverUrl");
        assert!(out.get("serverUrl").is_some());
        assert!(out.get("url").is_none());
        // command entry untouched
        let cmd = serde_json::json!({"command": "npx"});
        assert_eq!(remap_url_field(&cmd, "serverUrl"), cmd);
    }
}
