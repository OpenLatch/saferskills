//! Agent model + detection + writer dispatch.
//!
//! The canonical agent id set IS the backend `agent_compat.py::ALL_AGENTS`
//! enum (`schemas/catalog-item.schema.json::agentCompatibility`). The CLI's
//! `--to <agent>` flag accepts these kebab tokens; the legacy `codex-cli` /
//! `gemini-cli` ids are accepted as hidden aliases that warn + canonicalize.
//!
//! Detection ([`detect`]) runs every agent's validated probe and returns only
//! the agents actually present (a missing config = not installed — no false
//! positives). Writers ([`writer`] + [`writers`]) install/uninstall a
//! capability for a detected agent, recording every change for a clean reversal.

pub mod detect;
pub mod enumerate;
pub mod writer;
pub mod writers;

use std::path::PathBuf;

use serde::{Deserialize, Serialize};

use crate::core::error::{SsError, ERR_NO_AGENTS};

/// Canonical agent ids — the backend `ALL_AGENTS` set.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum AgentId {
    ClaudeCode,
    Cursor,
    Codex,
    Copilot,
    Windsurf,
    Cline,
    Gemini,
    Openclaw,
}

/// Every agent id, in catalog-enum order.
pub const ALL_AGENTS: [AgentId; 8] = [
    AgentId::ClaudeCode,
    AgentId::Cursor,
    AgentId::Codex,
    AgentId::Copilot,
    AgentId::Windsurf,
    AgentId::Cline,
    AgentId::Gemini,
    AgentId::Openclaw,
];

impl AgentId {
    /// The canonical kebab id (the `--to` token + the registry/telemetry value).
    pub fn as_str(self) -> &'static str {
        match self {
            AgentId::ClaudeCode => "claude-code",
            AgentId::Cursor => "cursor",
            AgentId::Codex => "codex",
            AgentId::Copilot => "copilot",
            AgentId::Windsurf => "windsurf",
            AgentId::Cline => "cline",
            AgentId::Gemini => "gemini",
            AgentId::Openclaw => "openclaw",
        }
    }

    /// Human display name for the detection list (`✓ Claude Code`).
    pub fn display_name(self) -> &'static str {
        match self {
            AgentId::ClaudeCode => "Claude Code",
            AgentId::Cursor => "Cursor",
            AgentId::Codex => "Codex",
            AgentId::Copilot => "GitHub Copilot",
            AgentId::Windsurf => "Windsurf",
            AgentId::Cline => "Cline",
            AgentId::Gemini => "Gemini",
            AgentId::Openclaw => "OpenClaw",
        }
    }

    /// The download/install URL shown when no agents are detected (CLI-9).
    pub fn download_url(self) -> &'static str {
        match self {
            AgentId::ClaudeCode => "https://claude.com/claude-code",
            AgentId::Cursor => "https://cursor.com",
            AgentId::Codex => "https://developers.openai.com/codex",
            AgentId::Copilot => "https://github.com/features/copilot",
            AgentId::Windsurf => "https://windsurf.com",
            AgentId::Cline => "https://cline.bot",
            AgentId::Gemini => "https://github.com/google-gemini/gemini-cli",
            AgentId::Openclaw => "https://openclaw.ai",
        }
    }

    /// Parse a canonical id from its kebab token (no alias handling).
    pub fn from_canonical(s: &str) -> Option<Self> {
        ALL_AGENTS.into_iter().find(|a| a.as_str() == s)
    }

    /// Parse a `--to` token. Accepts the canonical ids plus the two hidden legacy
    /// aliases (`codex-cli` → `codex`, `gemini-cli` → `gemini`), returning a
    /// warning string for an alias so the caller can nudge the user. An
    /// unknown token is `SS-E-1401` with a did-you-mean suggestion.
    pub fn parse_cli(s: &str) -> Result<(Self, Option<String>), SsError> {
        let lower = s.trim().to_ascii_lowercase();
        if let Some(id) = Self::from_canonical(&lower) {
            return Ok((id, None));
        }
        let canonical = match lower.as_str() {
            "codex-cli" => Some(AgentId::Codex),
            "gemini-cli" => Some(AgentId::Gemini),
            _ => None,
        };
        if let Some(id) = canonical {
            let warning = format!("`{s}` is the old id — using `{}`.", id.as_str());
            return Ok((id, Some(warning)));
        }
        Err(unknown_agent_error(s))
    }
}

impl std::fmt::Display for AgentId {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

fn unknown_agent_error(input: &str) -> SsError {
    let lower = input.to_ascii_lowercase();
    let suggestion = ALL_AGENTS
        .into_iter()
        .map(|a| (a, strsim::jaro_winkler(&lower, a.as_str())))
        .filter(|(_, score)| *score > 0.7)
        .max_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal))
        .map(|(a, _)| a.as_str());
    let known = ALL_AGENTS
        .iter()
        .map(|a| a.as_str())
        .collect::<Vec<_>>()
        .join(", ");
    let mut err = SsError::new(
        crate::core::error::ERR_UNKNOWN_AGENT,
        format!("Unknown agent: \"{input}\""),
    )
    .with_exit_code(2);
    err = match suggestion {
        Some(s) => err.with_suggestion(format!("Did you mean `{s}`? Known agents: {known}")),
        None => err.with_suggestion(format!("Known agents: {known}")),
    };
    err
}

/// Global (default) vs repo-local config scope.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Scope {
    Global,
    Project,
}

/// One detected agent + the paths a writer needs.
#[derive(Debug, Clone)]
pub struct DetectedAgent {
    pub id: AgentId,
    /// Best-effort version string (None when not cheaply knowable).
    pub version: Option<String>,
    /// The MCP config file to merge into for the resolved scope.
    pub mcp_config_path: PathBuf,
    /// The skills directory (None for agents with no skill concept).
    pub skill_dir: Option<PathBuf>,
    /// The rules directory a `rules` capability copies into (cursor / windsurf /
    /// cline / copilot). None for agents with no rules surface.
    pub rules_dir: Option<PathBuf>,
    /// The `settings.json` a `hook` capability merges into (claude-code /
    /// openclaw). None for agents with no hook surface.
    pub hooks_path: Option<PathBuf>,
    /// The `plugins/` root a `plugin` capability installs into (claude-code).
    /// None for agents with no plugin surface.
    pub plugin_dir: Option<PathBuf>,
    pub scope: Scope,
}

/// Run every agent's validated detection probe. Sequential — each
/// probe is a handful of filesystem `stat`s + PATH lookups (sub-millisecond);
/// parallelism would add a threading dependency for no measurable gain. De-dupes
/// naturally (one `DetectedAgent` per id).
pub fn detect_all(scope: Scope) -> Vec<DetectedAgent> {
    ALL_AGENTS
        .into_iter()
        .filter_map(|id| detect::detect(id, scope))
        .collect()
}

/// The no-agents-detected error (CLI-9) — lists every supported agent + a
/// download link.
pub fn no_agents_error() -> SsError {
    let mut lines = String::from("No supported agents detected. Install one of:\n");
    for a in ALL_AGENTS {
        lines.push_str(&format!(
            "    • {} — {}\n",
            a.display_name(),
            a.download_url()
        ));
    }
    SsError::new(
        ERR_NO_AGENTS,
        "No supported agents detected on this machine.",
    )
    .with_suggestion(lines)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn canonical_roundtrip() {
        for a in ALL_AGENTS {
            assert_eq!(AgentId::from_canonical(a.as_str()), Some(a));
        }
    }

    #[test]
    fn parse_cli_accepts_canonical() {
        let (id, warn) = AgentId::parse_cli("claude-code").unwrap();
        assert_eq!(id, AgentId::ClaudeCode);
        assert!(warn.is_none());
    }

    #[test]
    fn parse_cli_warns_on_legacy_alias() {
        let (id, warn) = AgentId::parse_cli("codex-cli").unwrap();
        assert_eq!(id, AgentId::Codex);
        assert!(warn.unwrap().contains("codex"));
        let (id, warn) = AgentId::parse_cli("gemini-cli").unwrap();
        assert_eq!(id, AgentId::Gemini);
        assert!(warn.is_some());
    }

    #[test]
    fn parse_cli_rejects_unknown_with_suggestion() {
        let err = AgentId::parse_cli("claudecode").unwrap_err();
        assert_eq!(err.code, crate::core::error::ERR_UNKNOWN_AGENT);
        assert_eq!(err.exit_code(), 2);
        assert!(err.suggestion.unwrap().contains("claude-code"));
    }

    #[test]
    fn serde_is_kebab() {
        let json = serde_json::to_string(&AgentId::ClaudeCode).unwrap();
        assert_eq!(json, "\"claude-code\"");
        let back: AgentId = serde_json::from_str("\"openclaw\"").unwrap();
        assert_eq!(back, AgentId::Openclaw);
    }

    #[test]
    fn no_agents_error_lists_all() {
        let err = no_agents_error();
        let s = err.suggestion.unwrap();
        for a in ALL_AGENTS {
            assert!(s.contains(a.display_name()), "{}", a.display_name());
        }
    }
}
