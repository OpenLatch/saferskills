//! Per-agent detection + path resolution (D-05-17, design.md §4 matrix).
//!
//! Each agent's [`detect`] arm validates by checking for a concrete signal — a
//! config file/dir or a binary on `PATH` — never a bare guess, so a missing
//! agent is reported absent (no false positives). The path helpers here are also
//! the single source the writers ([`super::writers`]) consume, so detection and
//! installation agree on exactly which files to touch.

use std::path::{Path, PathBuf};

use super::{AgentId, DetectedAgent, Scope};

/// Home directory (`%USERPROFILE%` on Windows via `dirs`).
fn home() -> Option<PathBuf> {
    dirs::home_dir()
}

/// The per-user config base — `%APPDATA%` (Windows), `~/Library/Application
/// Support` (macOS), `~/.config` (Linux). Exactly the VS Code globalStorage base
/// on all three.
fn config_base() -> Option<PathBuf> {
    dirs::config_dir()
}

/// Whether `bin` is found on `PATH` (honoring `PATHEXT` on Windows).
pub fn which(bin: &str) -> bool {
    let Some(paths) = std::env::var_os("PATH") else {
        return false;
    };
    let exts: Vec<String> = if cfg!(windows) {
        std::env::var("PATHEXT")
            .unwrap_or_else(|_| ".EXE;.CMD;.BAT;.COM".into())
            .split(';')
            .map(|e| e.to_ascii_lowercase())
            .collect()
    } else {
        vec![String::new()]
    };
    std::env::split_paths(&paths).any(|dir| {
        exts.iter().any(|ext| {
            let candidate = dir.join(format!("{bin}{ext}"));
            candidate.is_file()
        })
    })
}

fn cwd() -> PathBuf {
    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
}

/// The VS Code variant globalStorage base for the Cline extension, resolving the
/// installed variant dynamically (`Code` / `Code - Insiders` / `VSCodium`).
fn vscode_globalstorage(ext_id: &str) -> Option<PathBuf> {
    let base = config_base()?;
    for variant in ["Code", "Code - Insiders", "VSCodium"] {
        let dir = base
            .join(variant)
            .join("User")
            .join("globalStorage")
            .join(ext_id);
        if dir.exists() {
            return Some(dir);
        }
    }
    // None present yet → default to stable `Code` (creatable on install).
    Some(
        base.join("Code")
            .join("User")
            .join("globalStorage")
            .join(ext_id),
    )
}

/// Detect one agent for the requested scope, or `None` when it is not installed.
pub fn detect(id: AgentId, scope: Scope) -> Option<DetectedAgent> {
    match id {
        AgentId::ClaudeCode => claude_code(scope),
        AgentId::Cursor => cursor(scope),
        AgentId::Codex => codex(scope),
        AgentId::Copilot => copilot(scope),
        AgentId::Windsurf => windsurf(scope),
        AgentId::Cline => cline(scope),
        AgentId::Gemini => gemini(scope),
        AgentId::Openclaw => openclaw(scope),
    }
}

fn present(p: &Path) -> bool {
    p.exists()
}

fn claude_code(scope: Scope) -> Option<DetectedAgent> {
    let home = home()?;
    let dot = home.join(".claude");
    let dot_json = home.join(".claude.json");
    if !(present(&dot) || present(&dot_json) || which("claude")) {
        return None;
    }
    let (mcp_config_path, skill_dir) = match scope {
        Scope::Global => (dot_json, Some(dot.join("skills"))),
        Scope::Project => (
            cwd().join(".mcp.json"),
            Some(cwd().join(".claude").join("skills")),
        ),
    };
    Some(DetectedAgent {
        id: AgentId::ClaudeCode,
        version: None,
        mcp_config_path,
        skill_dir,
        scope,
    })
}

fn cursor(scope: Scope) -> Option<DetectedAgent> {
    let home = home()?;
    let dot = home.join(".cursor");
    if !(present(&dot) || which("cursor") || which("cursor-agent")) {
        return None;
    }
    let mcp_config_path = match scope {
        Scope::Global => dot.join("mcp.json"),
        Scope::Project => cwd().join(".cursor").join("mcp.json"),
    };
    Some(DetectedAgent {
        id: AgentId::Cursor,
        version: None,
        // Cursor has no native skills dir (it uses Rules) — skill installs surface
        // a copy-paste fallback via the writer's confidence.
        mcp_config_path,
        skill_dir: None,
        scope,
    })
}

fn codex(scope: Scope) -> Option<DetectedAgent> {
    let home = home()?;
    let dir = home.join(".codex");
    let cfg = dir.join("config.toml");
    if !(present(&cfg) || present(&dir) || which("codex")) {
        return None;
    }
    let mcp_config_path = match scope {
        Scope::Global => cfg,
        Scope::Project => cwd().join(".codex").join("config.toml"),
    };
    Some(DetectedAgent {
        id: AgentId::Codex,
        version: None,
        mcp_config_path,
        skill_dir: Some(dir.join("skills")),
        scope,
    })
}

fn copilot(scope: Scope) -> Option<DetectedAgent> {
    let home = home()?;
    let dir = home.join(".copilot");
    // CLI surface OR a VS Code project surface (.vscode/mcp.json under cwd).
    let project_vscode = cwd().join(".vscode").join("mcp.json");
    let detected = present(&dir) || which("copilot") || (present(&project_vscode));
    if !detected {
        return None;
    }
    let mcp_config_path = match scope {
        Scope::Global => dir.join("mcp-config.json"),
        Scope::Project => project_vscode,
    };
    Some(DetectedAgent {
        id: AgentId::Copilot,
        version: None,
        mcp_config_path,
        skill_dir: Some(dir.join("skills")),
        scope,
    })
}

fn windsurf(scope: Scope) -> Option<DetectedAgent> {
    let home = home()?;
    let dir = home.join(".codeium").join("windsurf");
    if !present(&dir) {
        return None;
    }
    // Windsurf MCP is global-only; the writer rejects --project explicitly.
    Some(DetectedAgent {
        id: AgentId::Windsurf,
        version: None,
        mcp_config_path: dir.join("mcp_config.json"),
        skill_dir: None,
        scope,
    })
}

fn cline(scope: Scope) -> Option<DetectedAgent> {
    let home = home()?;
    let gs = vscode_globalstorage("saoudrizwan.claude-dev");
    let dot_cline = home.join(".cline");
    let detected = gs.as_ref().is_some_and(|d| present(d)) || present(&dot_cline);
    if !detected {
        return None;
    }
    // VS Code globalStorage settings file (resolved variant), or the CLI's
    // ~/.cline/mcp.json when only that is present.
    let mcp_config_path = match gs {
        Some(dir) if present(&dir) || !present(&dot_cline) => {
            dir.join("settings").join("cline_mcp_settings.json")
        }
        _ => dot_cline.join("mcp.json"),
    };
    Some(DetectedAgent {
        id: AgentId::Cline,
        version: None,
        mcp_config_path,
        skill_dir: None,
        scope,
    })
}

fn gemini(scope: Scope) -> Option<DetectedAgent> {
    let home = home()?;
    let dir = home.join(".gemini");
    let settings = dir.join("settings.json");
    if !(present(&settings) || present(&dir) || which("gemini")) {
        return None;
    }
    let mcp_config_path = match scope {
        Scope::Global => settings,
        Scope::Project => cwd().join(".gemini").join("settings.json"),
    };
    Some(DetectedAgent {
        id: AgentId::Gemini,
        version: None,
        mcp_config_path,
        skill_dir: Some(dir.join("skills")),
        scope,
    })
}

fn openclaw(scope: Scope) -> Option<DetectedAgent> {
    let home = home()?;
    let dir = home.join(".openclaw");
    let cfg = dir.join("openclaw.json");
    if !(present(&cfg) || present(&dir) || which("openclaw")) {
        return None;
    }
    let mcp_config_path = match scope {
        Scope::Global => cfg,
        Scope::Project => cwd().join(".mcp.json"),
    };
    Some(DetectedAgent {
        id: AgentId::Openclaw,
        version: None,
        mcp_config_path,
        skill_dir: Some(dir.join("skills")),
        scope,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn which_finds_nothing_for_a_bogus_binary() {
        assert!(!which("a-binary-that-cannot-possibly-exist-xyz"));
    }

    #[test]
    fn detect_returns_paths_or_none_without_panicking() {
        // `dirs::home_dir()` reads the OS API (not an env var) on Windows, so a
        // fake-HOME test is unreliable cross-platform. We assert the contract that
        // holds everywhere: a detected agent carries an MCP config path, and the
        // resolved scope is preserved.
        for id in super::super::ALL_AGENTS {
            if let Some(d) = detect(id, Scope::Global) {
                assert_eq!(d.id, id);
                assert_eq!(d.scope, Scope::Global);
                assert!(!d.mcp_config_path.as_os_str().is_empty());
            }
        }
    }
}
