//! The eight per-agent config writers.
//!
//! Each agent module documents its config-key + URL-field landmines (the
//! load-bearing per-agent differences) and constructs a writer
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
pub mod render;
pub mod windsurf;

use std::path::{Path, PathBuf};

use serde_json::Value;

use self::render::{render_skill, SkillRender};
use super::writer::{
    install_plugin, install_rules_file, kind_supported, merge_json_hook, merge_json_mcp,
    merge_marker_block, merge_toml_mcp, openclaw_key, reject_project_if_unsupported,
    revert_changes, verify_hook, verify_json_mcp, verify_plugin, verify_toml_mcp,
    write_file_change, Confidence, ConfigWriter, ResolvedItem, VerifyStatus,
};
use super::{AgentId, DetectedAgent, Scope};
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
    /// The per-agent rules-file extension (`.mdc` Cursor, `.md` Windsurf/Cline,
    /// `.instructions.md` Copilot). Empty for agents with no rules surface.
    pub rules_ext: &'static str,
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

fn no_rules_dir_err(id: AgentId) -> SsError {
    SsError::new(
        ERR_WRITER_UNSUPPORTED,
        format!(
            "{} has no rules directory for a rules install.",
            id.display_name()
        ),
    )
    .with_suggestion("This capability can't be auto-installed for this agent; copy it in manually.")
}

fn no_hooks_err(id: AgentId) -> SsError {
    SsError::new(
        ERR_WRITER_UNSUPPORTED,
        format!(
            "{} has no settings file for a hook install.",
            id.display_name()
        ),
    )
}

fn no_plugin_dir_err(id: AgentId) -> SsError {
    SsError::new(
        ERR_WRITER_UNSUPPORTED,
        format!(
            "{} has no plugins directory for a plugin install.",
            id.display_name()
        ),
    )
}

/// The rules file name an agent writes for capability `name` (`<name><ext>`).
fn rules_file_name(name: &str, ext: &str) -> String {
    let stem: String = name
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.' {
                c
            } else {
                '-'
            }
        })
        .collect();
    let stem = stem.trim_matches('-');
    format!("{}{ext}", if stem.is_empty() { "rules" } else { stem })
}

/// The hook event names carried on a resolved item's `hook_entry` block (its keys).
fn hook_event_names(item: &ResolvedItem) -> Vec<String> {
    item.hook_entry
        .as_ref()
        .and_then(|v| v.as_object())
        .map(|o| o.keys().cloned().collect())
        .unwrap_or_default()
}

/// Agents whose skill form is a marker block merged into a shared `AGENTS.md` /
/// `GEMINI.md` (no skills dir, no rules dir of their own for a skill) — Codex,
/// Copilot, Gemini. Used by both `render_skill` dispatch and `kind_supported`,
/// and by `uninstall::agent_dirs` to scope the shared-host change to its owners.
pub(crate) fn is_agents_md_agent(id: AgentId) -> bool {
    matches!(id, AgentId::Codex | AgentId::Copilot | AgentId::Gemini)
}

/// The standalone-file destination for a `SkillRender::File` form (plan 02):
/// - Claude Code / OpenClaw → `<skill_dir>/saferskills/SKILL.md` (verbatim).
/// - Cursor → `<rules_dir>/saferskills.mdc` (Agent-Requested `.mdc`).
/// - Cline / Windsurf → `<rules_dir>/saferskills.md` (always-on rules).
fn skill_target_path(id: AgentId, agent: &DetectedAgent) -> Result<PathBuf, SsError> {
    match id {
        AgentId::ClaudeCode | AgentId::Openclaw => agent
            .skill_dir
            .as_ref()
            .map(|d| d.join("saferskills").join("SKILL.md"))
            .ok_or_else(|| no_skill_dir_err(id)),
        AgentId::Cursor => agent
            .rules_dir
            .as_ref()
            .map(|d| d.join("saferskills.mdc"))
            .ok_or_else(|| no_rules_dir_err(id)),
        AgentId::Cline | AgentId::Windsurf => agent
            .rules_dir
            .as_ref()
            .map(|d| d.join("saferskills.md"))
            .ok_or_else(|| no_rules_dir_err(id)),
        // Codex/Copilot/Gemini render a Block, never a File — unreachable in the
        // dispatch, but keep the match total with a clear error.
        AgentId::Codex | AgentId::Copilot | AgentId::Gemini => Err(no_skill_dir_err(id)),
    }
}

/// The shared host file a `SkillRender::Block` merges into (plan 02, Module D).
/// `GEMINI.md`/`AGENTS.md` at the project root (the file Codex + Copilot both
/// read — shared, idempotent) or in the agent's home dir for a global install.
pub(crate) fn agents_md_path(id: AgentId, agent: &DetectedAgent) -> Result<PathBuf, SsError> {
    let file = if id == AgentId::Gemini {
        "GEMINI.md"
    } else {
        "AGENTS.md"
    };
    match agent.scope {
        Scope::Project => Ok(std::env::current_dir()
            .map_err(|e| {
                SsError::new(
                    ERR_WRITER_UNSUPPORTED,
                    format!("Cannot resolve the project directory: {e}"),
                )
            })?
            .join(file)),
        // Global: the agent's home (skill_dir parent: ~/.codex, ~/.gemini, ~/.copilot).
        Scope::Global => agent
            .skill_dir
            .as_ref()
            .and_then(|d| d.parent())
            .map(|p| p.join(file))
            .ok_or_else(|| no_skill_dir_err(id)),
    }
}

/// Verify a rendered skill install (plan 02) — the standalone file exists, or the
/// shared `AGENTS.md` / `GEMINI.md` carries our marker block. Path-only (no
/// `skill_md` needed), so `doctor`'s sparse `ResolvedItem` verifies correctly.
fn verify_skill_rendered(id: AgentId, agent: &DetectedAgent) -> VerifyStatus {
    if is_agents_md_agent(id) {
        let Ok(host) = agents_md_path(id, agent) else {
            return VerifyStatus::Missing;
        };
        // Require a COMPLETE block — a lone orphan start is NOT a valid install.
        match std::fs::read_to_string(&host) {
            Ok(s) if super::writer::has_complete_marker_block(&s) => VerifyStatus::Ok,
            _ => VerifyStatus::Missing,
        }
    } else {
        match skill_target_path(id, agent) {
            Ok(dest) if dest.exists() => VerifyStatus::Ok,
            _ => VerifyStatus::Missing,
        }
    }
}

/// Dispatch a resolved skill to its native form for `id`/`agent` and write it,
/// returning the recorded change(s). Shared by both writers' `"skill"` arm.
fn install_skill_rendered(
    id: AgentId,
    item: &ResolvedItem,
    agent: &DetectedAgent,
    dry_run: bool,
) -> Result<Vec<InstallChange>, SsError> {
    let skill_md = item.skill_md.as_ref().ok_or_else(|| no_entry_err(id))?;
    match render_skill(skill_md, id)? {
        SkillRender::File { content } => {
            let dest = skill_target_path(id, agent)?;
            Ok(vec![write_file_change(&dest, content.as_bytes(), dry_run)?])
        }
        SkillRender::Block { block } => {
            let host = agents_md_path(id, agent)?;
            Ok(vec![merge_marker_block(&host, &block, dry_run)?])
        }
    }
}

impl ConfigWriter for JsonMcpWriter {
    fn id(&self) -> AgentId {
        self.id
    }
    fn confidence(&self) -> Confidence {
        self.confidence
    }
    fn supports_kind(&self, kind: &str, agent: &DetectedAgent) -> bool {
        kind_supported(kind, agent)
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
            "skill" => install_skill_rendered(self.id, item, agent, dry_run),
            "rules" => {
                let rules_dir = agent
                    .rules_dir
                    .as_ref()
                    .ok_or_else(|| no_rules_dir_err(self.id))?;
                let body = item
                    .rules_body
                    .as_ref()
                    .ok_or_else(|| no_entry_err(self.id))?;
                let file = rules_file_name(&item.name, self.rules_ext);
                Ok(vec![install_rules_file(rules_dir, &file, body, dry_run)?])
            }
            "hook" => {
                let settings = agent
                    .hooks_path
                    .as_ref()
                    .ok_or_else(|| no_hooks_err(self.id))?;
                let entry = item
                    .hook_entry
                    .as_ref()
                    .ok_or_else(|| no_entry_err(self.id))?;
                merge_json_hook(settings, entry, dry_run)
            }
            "plugin" => {
                let plugins_root = agent
                    .plugin_dir
                    .as_ref()
                    .ok_or_else(|| no_plugin_dir_err(self.id))?;
                let zip = item
                    .plugin_zip
                    .as_ref()
                    .ok_or_else(|| no_entry_err(self.id))?;
                let mp = item.plugin_marketplace.as_deref().unwrap_or("saferskills");
                let version = item.plugin_version.as_deref().unwrap_or("0.0.0");
                let component = item.component_path.as_deref().unwrap_or("");
                install_plugin(
                    plugins_root,
                    mp,
                    &item.name,
                    version,
                    component,
                    zip,
                    dry_run,
                )
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
            "skill" => verify_skill_rendered(self.id, agent),
            "rules" => match agent.rules_dir.as_ref() {
                Some(dir)
                    if dir
                        .join(rules_file_name(&item.name, self.rules_ext))
                        .exists() =>
                {
                    VerifyStatus::Ok
                }
                _ => VerifyStatus::Missing,
            },
            "hook" => match agent.hooks_path.as_ref() {
                Some(p) => verify_hook(p, &hook_event_names(item)),
                None => VerifyStatus::Missing,
            },
            "plugin" => match agent.plugin_dir.as_ref() {
                Some(root) => verify_plugin(
                    root,
                    item.plugin_marketplace.as_deref().unwrap_or("saferskills"),
                    &item.name,
                    item.plugin_version.as_deref().unwrap_or("0.0.0"),
                ),
                None => VerifyStatus::Missing,
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
        kind_supported(kind, agent)
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
            "skill" => install_skill_rendered(AgentId::Codex, item, agent, dry_run),
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
            "skill" => verify_skill_rendered(AgentId::Codex, agent),
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
