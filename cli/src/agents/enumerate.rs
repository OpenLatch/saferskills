//! Local-install enumeration — audit every capability *already installed* across
//! detected agents (D-05-27).
//!
//! `scan --local` answers "audit everything I have installed", which is a
//! different question from the CLI's own install ledger (`core::registry`, which
//! only knows what *saferskills* installed). This module reads each detected
//! agent's *own* config dirs/files — `agent.skill_dir`, `agent.mcp_config_path`,
//! and the command / subagent / hook / rules / plugin-cache roots derived from
//! them — and emits one [`LocalCapability`] per skill / MCP server / hook / rules
//! file / command / subagent / installed-plugin found, regardless of how it was
//! installed. The result is bundled into one structured `.zip` (paths matching
//! the backend `discovery.py` anchor layout) and uploaded once.
//!
//! **Slash commands + subagents map to the `skill` kind.** The backend kind set
//! is closed (`skill, mcp_server, hook, plugin, rules` — no `command`/`agent`),
//! and Claude's own docs treat commands and skills as the same mechanism, so each
//! `commands/*.md` / `agents/*.md` (and Codex `prompts/*.md`, Gemini
//! `commands/*.toml`) is synthesized as a `SKILL.md` anchor and scored by the 25
//! `SS-SKILL-*` rules. A namespaced command (`commands/lde/x.md`) keeps its
//! `lde:x` name via a `name:` frontmatter prepend (only when the source has no
//! frontmatter of its own).
//!
//! **The Claude plugin cache** (`~/.claude/plugins/cache/<mp>/<plugin>/<ver>/`)
//! is decomposed: each active-version plugin's bundled `skills/`, `.mcp.json`,
//! `hooks/`, `commands/`, `agents/`, and `.claude-plugin/plugin.json` become
//! their own scored capabilities (one bundle → many caps). Only the
//! installed-active version is read (per `installed_plugins.json`); lock/vendor/
//! binary dirs are excluded.
//!
//! **Testable seam.** [`enumerate_local`] resolves the detected agents (which
//! reads `dirs::home_dir()` — not a fake-HOME-friendly env var, see `detect.rs`
//! tests) and delegates to [`enumerate_from`], whose `discover_*` helpers read
//! ONLY the paths on the [`DetectedAgent`]s handed in. Unit tests build
//! tempdir-rooted agents for deterministic results.
//!
//! Every discovery helper is **infallible** — a malformed config, an unreadable
//! file, or an oversized blob becomes a [`SkipNote`], never an `Err`: one bad
//! capability never fails the whole audit.

use std::collections::HashSet;
use std::path::{Path, PathBuf};

use serde_json::Value;

use super::writer;
use super::{detect_all, AgentId, DetectedAgent, Scope};

/// The capability kinds a local audit enumerates. `as_str()` → the snake_case
/// backend kind. Commands + subagents are emitted as `Skill`; an installed
/// plugin's manifest is emitted as `Plugin` (its nested caps by their real kind).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CapKind {
    Skill,
    McpServer,
    Hook,
    Rules,
    Plugin,
}

impl CapKind {
    /// The backend snake_case kind id.
    pub fn as_str(self) -> &'static str {
        match self {
            CapKind::Skill => "skill",
            CapKind::McpServer => "mcp_server",
            CapKind::Hook => "hook",
            CapKind::Rules => "rules",
            CapKind::Plugin => "plugin",
        }
    }

    /// Budget priority when the total budget is tight — lower = kept first
    /// (`mcp_server > skill > hook > rules > plugin`).
    pub fn priority(self) -> u8 {
        match self {
            CapKind::McpServer => 0,
            CapKind::Skill => 1,
            CapKind::Hook => 2,
            CapKind::Rules => 3,
            CapKind::Plugin => 4,
        }
    }
}

/// One installed capability discovered on disk, ready to bundle. `entries` are
/// the synthetic `.zip` rel-paths (each already prefixed with the agent id, so
/// same-named caps across agents never collide) → file bytes; `anchor` is the
/// one entry the backend needs to detect the capability (always kept).
#[derive(Debug, Clone)]
pub struct LocalCapability {
    pub agent: AgentId,
    pub kind: CapKind,
    pub name: String,
    /// The real filesystem origin (config file or capability dir) — display only.
    pub origin: PathBuf,
    /// The synthetic rel-path of the anchor file (always included in the bundle).
    pub anchor: String,
    /// Synthetic rel-path → bytes (includes the anchor).
    pub entries: Vec<(String, Vec<u8>)>,
    /// Sum of entry byte lengths.
    pub bytes: usize,
}

impl LocalCapability {
    /// Stable CLI-side identity of this capability's bytes (NOT the server hash
    /// — only used to correlate `list` ↔ the local scan cache, `core::scan_cache`).
    /// sha256 over the sorted `(rel_path, bytes)` entries, length-prefixing each
    /// field so no concatenation ambiguity can collide two distinct trees.
    /// Determinism only needs to match itself across runs — `list` and
    /// `scan --local` both call it on the same enumerated entries.
    pub fn content_hash(&self) -> String {
        use sha2::{Digest, Sha256};
        let mut entries: Vec<&(String, Vec<u8>)> = self.entries.iter().collect();
        entries.sort_by(|a, b| a.0.cmp(&b.0));
        let mut hasher = Sha256::new();
        for (rel, bytes) in entries {
            hasher.update((rel.len() as u64).to_le_bytes());
            hasher.update(rel.as_bytes());
            hasher.update((bytes.len() as u64).to_le_bytes());
            hasher.update(bytes);
        }
        let digest: [u8; 32] = hasher.finalize().into();
        digest.iter().map(|b| format!("{b:02x}")).collect()
    }
}

/// Why a file or capability was left out of the bundle.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SkipReason {
    Binary,
    NestedArchive,
    VendorDir,
    TooLargeFile,
    CapTooLarge,
    BudgetFull,
    MalformedConfig,
    Unreadable,
}

impl SkipReason {
    /// A short human label for the pre-flight skip summary.
    pub fn label(self) -> &'static str {
        match self {
            SkipReason::Binary => "binary",
            SkipReason::NestedArchive => "nested archive",
            SkipReason::VendorDir => "vendor dir",
            SkipReason::TooLargeFile => "oversized file",
            SkipReason::CapTooLarge => "capability over size cap",
            SkipReason::BudgetFull => "bundle budget full",
            SkipReason::MalformedConfig => "malformed config",
            SkipReason::Unreadable => "unreadable",
        }
    }

    /// The stable snake_case token for the `--json` skip list.
    pub fn as_str(self) -> &'static str {
        match self {
            SkipReason::Binary => "binary",
            SkipReason::NestedArchive => "nested_archive",
            SkipReason::VendorDir => "vendor_dir",
            SkipReason::TooLargeFile => "too_large_file",
            SkipReason::CapTooLarge => "cap_too_large",
            SkipReason::BudgetFull => "budget_full",
            SkipReason::MalformedConfig => "malformed_config",
            SkipReason::Unreadable => "unreadable",
        }
    }
}

/// One skipped path + why.
#[derive(Debug, Clone)]
pub struct SkipNote {
    pub agent: Option<AgentId>,
    pub path: String,
    pub reason: SkipReason,
}

impl SkipNote {
    fn at(agent: AgentId, path: impl Into<String>, reason: SkipReason) -> Self {
        Self {
            agent: Some(agent),
            path: path.into(),
            reason,
        }
    }
}

/// The discovery result — capabilities found + per-file/config skips.
#[derive(Debug, Clone, Default)]
pub struct Enumeration {
    pub capabilities: Vec<LocalCapability>,
    pub skips: Vec<SkipNote>,
}

// ─── size-control budget ─────────────────────────────────────────────────────

/// Bundle size caps. The binding backend limit is the **10 MiB compressed** body
/// (text deflates 3–5×), so a 32 MiB text budget stays well under it; the
/// per-file / per-cap / entry caps keep one fat skill from eating the whole
/// bundle. (Backend decompressed caps are 1000 entries / 5 MiB-file / 50 MiB.)
pub mod budget {
    pub const MAX_FILE_BYTES: usize = 1024 * 1024; // 1 MiB
    pub const MAX_CAPABILITY_BYTES: usize = 4 * 1024 * 1024; // 4 MiB
    pub const MAX_TOTAL_BYTES: usize = 32 * 1024 * 1024; // 32 MiB
    /// The binding ceiling on the local-audit `.zip` is the BACKEND's per-upload
    /// entry cap (`upload_extract_max_entries`, default 1000) — a bundle over it
    /// is rejected whole with `422 archive_rejected (entries)`. We mirror that
    /// exact value (not the byte budget, which a deep plugin cache reaches far
    /// later) so the priority loop trims lowest-priority caps first and reports
    /// `BudgetFull` skips, rather than building a zip the server refuses. Raise
    /// both ends together if the backend cap ever moves. (The CLI dedups + drops
    /// `.git` identically to the backend, so the two entry counts agree.)
    pub const MAX_ENTRIES: usize = 1000;

    /// Directories never bundled (VCS / build / dependency vendor trees, and
    /// plugin runtime lock dirs — `.in_use` holds hundreds of transient PID files).
    pub const EXCLUDED_DIRS: &[&str] = &[
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        "dist",
        "build",
        "target",
        ".next",
        ".turbo",
        ".cache",
        "vendor",
        ".idea",
        "coverage",
        ".gradle",
        ".in_use",
    ];

    /// Nested-archive extensions — bundling one would trip the backend's
    /// `422 nesting` (archive-in-upload) guard, so drop it.
    pub const ARCHIVE_EXTS: &[&str] = &[
        "zip", "gz", "tar", "tgz", "tbz", "bz2", "7z", "rar", "xz", "zst",
    ];

    /// Binary / media extensions never worth scanning as text.
    pub const BINARY_EXTS: &[&str] = &[
        "exe", "dll", "so", "dylib", "bin", "wasm", "node", "class", "jar", "pyc", "png", "jpg",
        "jpeg", "gif", "webp", "svg", "ico", "mp4", "mp3", "wav", "mov", "pdf", "woff", "woff2",
        "ttf", "otf", "map",
    ];
}

/// NUL byte in the first 8 KiB, or >30% control bytes → treat as binary.
fn looks_binary(bytes: &[u8]) -> bool {
    let window = &bytes[..bytes.len().min(8192)];
    if window.is_empty() {
        return false;
    }
    if window.contains(&0) {
        return true;
    }
    let control = window
        .iter()
        .filter(|b| (**b < 0x09) || (**b > 0x0d && **b < 0x20))
        .count();
    control * 100 / window.len() > 30
}

/// Lowercase final extension of a rel-path (no dot), if any.
fn ext_of(rel: &str) -> Option<String> {
    let base = rel.rsplit('/').next().unwrap_or(rel);
    base.rsplit_once('.').map(|(_, e)| e.to_ascii_lowercase())
}

/// A skip reason for an excluded extension, or `None` to keep.
fn excluded_ext_reason(rel: &str) -> Option<SkipReason> {
    let ext = ext_of(rel)?;
    if budget::ARCHIVE_EXTS.contains(&ext.as_str()) {
        Some(SkipReason::NestedArchive)
    } else if budget::BINARY_EXTS.contains(&ext.as_str()) {
        Some(SkipReason::Binary)
    } else {
        None
    }
}

fn is_excluded_dir(name: &str) -> bool {
    budget::EXCLUDED_DIRS.contains(&name)
}

// ─── public entry points ─────────────────────────────────────────────────────

/// Enumerate every installed capability across the detected agents for `scope`.
pub fn enumerate_local(scope: Scope) -> Enumeration {
    enumerate_from(&detect_all(scope))
}

/// The unit-tested core — discovers from the agents handed in, reading ONLY
/// their paths (never `dirs::home_dir()`).
pub fn enumerate_from(agents: &[DetectedAgent]) -> Enumeration {
    let mut capabilities = Vec::new();
    let mut skips = Vec::new();
    for agent in agents {
        discover_skills(agent, &mut capabilities, &mut skips);
        discover_mcp(agent, &mut capabilities, &mut skips);
        discover_hooks(agent, &mut capabilities, &mut skips);
        discover_rules(agent, &mut capabilities, &mut skips);
        discover_commands(agent, &mut capabilities, &mut skips);
        discover_subagents(agent, &mut capabilities, &mut skips);
        discover_plugins(agent, &mut capabilities, &mut skips);
    }
    Enumeration {
        capabilities,
        skips,
    }
}

// ─── discovery: skills ───────────────────────────────────────────────────────

fn discover_skills(
    agent: &DetectedAgent,
    out: &mut Vec<LocalCapability>,
    skips: &mut Vec<SkipNote>,
) {
    let Some(skill_dir) = agent.skill_dir.as_ref() else {
        return;
    };
    let mount = format!("{}/skills", agent.id.as_str());
    scan_skills_dir(skill_dir, &mount, agent.id, out, skips);
}

/// Walk a skills directory: each child dir containing a `SKILL.md` becomes one
/// [`CapKind::Skill`] capability mounted at `<mount>/<name>`. Root-relative +
/// reusable — used both at the agent's `skill_dir` and inside a plugin's
/// `skills/` payload.
fn scan_skills_dir(
    skills_dir: &Path,
    mount: &str,
    agent: AgentId,
    out: &mut Vec<LocalCapability>,
    skips: &mut Vec<SkipNote>,
) {
    if !skills_dir.is_dir() {
        return; // no skills installed here
    }
    let mut children: Vec<PathBuf> = match std::fs::read_dir(skills_dir) {
        Ok(rd) => rd.filter_map(|e| e.ok().map(|e| e.path())).collect(),
        Err(_) => {
            skips.push(SkipNote::at(
                agent,
                skills_dir.to_string_lossy(),
                SkipReason::Unreadable,
            ));
            return;
        }
    };
    children.sort();
    for child in children {
        if !child.is_dir() {
            continue;
        }
        let Some(anchor_name) = find_anchor_file(&child, "skill.md") else {
            continue; // a dir without SKILL.md is not a skill
        };
        let name = child
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("skill")
            .to_string();
        let cap_mount = format!("{mount}/{name}");
        let anchor = format!("{cap_mount}/{anchor_name}");
        if let Some(cap) = collect_dir_capability(
            agent,
            CapKind::Skill,
            &name,
            &child,
            &cap_mount,
            &anchor,
            skips,
        ) {
            out.push(cap);
        }
    }
}

/// Find a file in `dir` whose name case-insensitively equals `target` (e.g.
/// `SKILL.md`/`skill.md`), returning its real on-disk name.
fn find_anchor_file(dir: &Path, target_lower: &str) -> Option<String> {
    let rd = std::fs::read_dir(dir).ok()?;
    for entry in rd.flatten() {
        let p = entry.path();
        if p.is_file() {
            if let Some(name) = p.file_name().and_then(|n| n.to_str()) {
                if name.to_ascii_lowercase() == target_lower {
                    return Some(name.to_string());
                }
            }
        }
    }
    None
}

// ─── discovery: MCP servers ──────────────────────────────────────────────────

fn discover_mcp(agent: &DetectedAgent, out: &mut Vec<LocalCapability>, skips: &mut Vec<SkipNote>) {
    let path = &agent.mcp_config_path;
    if !path.is_file() {
        return; // no MCP config installed
    }
    let mount = format!("{}/mcp", agent.id.as_str());
    if agent.id == AgentId::Codex {
        discover_mcp_toml(agent, &mount, out, skips);
        return;
    }
    let key = mcp_key_path(agent);
    let key_refs: Vec<&str> = key.iter().map(String::as_str).collect();
    scan_mcp_file(path, &key_refs, &mount, agent.id, out, skips);
}

/// Extract every MCP server from a JSON/JSONC config under `key_path`, mounting
/// each at `<mount>/<server>/mcp.json`. Root-relative + reusable — used both for
/// an agent's own MCP config and a plugin's bundled `.mcp.json`.
fn scan_mcp_file(
    path: &Path,
    key_path: &[&str],
    mount: &str,
    agent: AgentId,
    out: &mut Vec<LocalCapability>,
    skips: &mut Vec<SkipNote>,
) {
    if !path.is_file() {
        return;
    }
    let text = match std::fs::read_to_string(path) {
        Ok(t) => t,
        Err(_) => {
            skips.push(SkipNote::at(
                agent,
                path.to_string_lossy(),
                SkipReason::Unreadable,
            ));
            return;
        }
    };
    let value = match parse_jsonc(&text) {
        Some(v) => v,
        None => {
            skips.push(SkipNote::at(
                agent,
                path.to_string_lossy(),
                SkipReason::MalformedConfig,
            ));
            return;
        }
    };
    let Some(map) = navigate_object(&value, key_path) else {
        return; // no server map under the expected key — nothing installed
    };
    for (name, entry) in map {
        out.push(make_mcp_cap(agent, path, name, entry, mount));
    }
}

fn discover_mcp_toml(
    agent: &DetectedAgent,
    mount: &str,
    out: &mut Vec<LocalCapability>,
    skips: &mut Vec<SkipNote>,
) {
    let path = &agent.mcp_config_path;
    let text = match std::fs::read_to_string(path) {
        Ok(t) => t,
        Err(_) => {
            skips.push(SkipNote::at(
                agent.id,
                path.to_string_lossy(),
                SkipReason::Unreadable,
            ));
            return;
        }
    };
    let doc = match text.parse::<toml_edit::DocumentMut>() {
        Ok(d) => d,
        Err(_) => {
            skips.push(SkipNote::at(
                agent.id,
                path.to_string_lossy(),
                SkipReason::MalformedConfig,
            ));
            return;
        }
    };
    let Some(servers) = doc.get("mcp_servers").and_then(|i| i.as_table()) else {
        return;
    };
    for (name, item) in servers.iter() {
        let entry = writer::toml_to_json(item);
        out.push(make_mcp_cap(agent.id, path, name, &entry, mount));
    }
}

/// The object key-path holding the MCP server map, per the agent's config shape
/// (mirrors the writer's resolution in `writer.rs` / `SCHEMAS.md`).
fn mcp_key_path(agent: &DetectedAgent) -> Vec<String> {
    match agent.id {
        AgentId::Openclaw => writer::openclaw_key(&agent.mcp_config_path)
            .iter()
            .map(|s| s.to_string())
            .collect(),
        AgentId::Copilot => {
            // VS Code surface uses `servers`; the CLI surface uses `mcpServers`.
            if agent
                .mcp_config_path
                .components()
                .any(|c| c.as_os_str() == ".vscode")
            {
                vec!["servers".to_string()]
            } else {
                vec!["mcpServers".to_string()]
            }
        }
        _ => vec!["mcpServers".to_string()],
    }
}

/// One synthetic `mcp.json` per server: `{"name": <server>, "server": <entry>}`
/// — the backend reads `name` for the capability name + the dir as the anchor.
/// `mount` is the parent path the server dir hangs under (`<agent>/mcp` or a
/// plugin's `<…>/plugins/<mp>__<plugin>/mcp`).
fn make_mcp_cap(
    agent: AgentId,
    origin: &Path,
    name: &str,
    entry: &Value,
    mount: &str,
) -> LocalCapability {
    let seg = sanitize_segment(name);
    let mount = format!("{mount}/{seg}");
    let anchor = format!("{mount}/mcp.json");
    let body = serde_json::json!({ "name": name, "server": entry });
    let bytes = serde_json::to_vec_pretty(&body).unwrap_or_default();
    let len = bytes.len();
    LocalCapability {
        agent,
        kind: CapKind::McpServer,
        name: name.to_string(),
        origin: origin.to_path_buf(),
        anchor: anchor.clone(),
        entries: vec![(anchor, bytes)],
        bytes: len,
    }
}

// ─── discovery: hooks (Claude Code only, v1) ─────────────────────────────────

fn discover_hooks(
    agent: &DetectedAgent,
    out: &mut Vec<LocalCapability>,
    skips: &mut Vec<SkipNote>,
) {
    if agent.id != AgentId::ClaudeCode {
        return;
    }
    // The Claude config root is the parent of the skills dir (`~/.claude`).
    let Some(claude_root) = agent.skill_dir.as_ref().and_then(|d| d.parent()) else {
        return;
    };
    let agent_seg = agent.id.as_str();

    // settings.json declaring a `hooks` block.
    let settings = claude_root.join("settings.json");
    if settings.is_file() {
        match std::fs::read(&settings) {
            Ok(bytes) => match parse_jsonc(&String::from_utf8_lossy(&bytes)) {
                Some(v) if v.get("hooks").is_some() => {
                    let synth = format!("{agent_seg}/.claude/settings.json");
                    out.push(single_file_cap(
                        agent.id,
                        CapKind::Hook,
                        "settings",
                        &settings,
                        synth,
                        bytes,
                    ));
                }
                Some(_) => {} // no hooks key → not a hook
                None => skips.push(SkipNote::at(
                    agent.id,
                    settings.to_string_lossy(),
                    SkipReason::MalformedConfig,
                )),
            },
            Err(_) => skips.push(SkipNote::at(
                agent.id,
                settings.to_string_lossy(),
                SkipReason::Unreadable,
            )),
        }
    }

    // hooks/*.json — each json under a `hooks/` dir is a hook anchor.
    let hooks_dir = claude_root.join("hooks");
    let hooks_mount = format!("{agent_seg}/hooks");
    scan_hooks_dir(&hooks_dir, &hooks_mount, agent.id, out, skips);
}

/// Walk a `hooks/` directory: each `*.json` is a hook anchor mounted at
/// `<mount>/<file>.json`. Root-relative + reusable — used both at
/// `~/.claude/hooks` and inside a plugin's `hooks/` payload.
fn scan_hooks_dir(
    hooks_dir: &Path,
    mount: &str,
    agent: AgentId,
    out: &mut Vec<LocalCapability>,
    skips: &mut Vec<SkipNote>,
) {
    if !hooks_dir.is_dir() {
        return;
    }
    let mut files: Vec<PathBuf> = match std::fs::read_dir(hooks_dir) {
        Ok(rd) => rd.filter_map(|e| e.ok().map(|e| e.path())).collect(),
        Err(_) => vec![],
    };
    files.sort();
    for path in files {
        if !path.is_file() {
            continue;
        }
        let fname = path.file_name().and_then(|n| n.to_str()).unwrap_or("");
        if !fname.to_ascii_lowercase().ends_with(".json") {
            continue;
        }
        let stem = fname.rsplit_once('.').map(|(s, _)| s).unwrap_or(fname);
        match std::fs::read(&path) {
            Ok(bytes) => {
                let synth = format!("{mount}/{fname}");
                out.push(single_file_cap(
                    agent,
                    CapKind::Hook,
                    stem,
                    &path,
                    synth,
                    bytes,
                ));
            }
            Err(_) => skips.push(SkipNote::at(
                agent,
                path.to_string_lossy(),
                SkipReason::Unreadable,
            )),
        }
    }
}

// ─── discovery: rules (Cursor, v1) ───────────────────────────────────────────

fn discover_rules(
    agent: &DetectedAgent,
    out: &mut Vec<LocalCapability>,
    _skips: &mut Vec<SkipNote>,
) {
    if agent.id != AgentId::Cursor {
        return;
    }
    // The Cursor config root is the parent of the MCP config (`~/.cursor`).
    let Some(cursor_root) = agent.mcp_config_path.parent() else {
        return;
    };
    let agent_seg = agent.id.as_str();

    // .cursor/rules/*.mdc
    let rules_dir = cursor_root.join("rules");
    if rules_dir.is_dir() {
        let mut files: Vec<PathBuf> = match std::fs::read_dir(&rules_dir) {
            Ok(rd) => rd.filter_map(|e| e.ok().map(|e| e.path())).collect(),
            Err(_) => vec![],
        };
        files.sort();
        for path in files {
            if !path.is_file() {
                continue;
            }
            let fname = path.file_name().and_then(|n| n.to_str()).unwrap_or("");
            if !fname.to_ascii_lowercase().ends_with(".mdc") {
                continue;
            }
            let stem = fname.rsplit_once('.').map(|(s, _)| s).unwrap_or(fname);
            if let Ok(bytes) = std::fs::read(&path) {
                let synth = format!("{agent_seg}/.cursor/rules/{fname}");
                out.push(single_file_cap(
                    agent.id,
                    CapKind::Rules,
                    stem,
                    &path,
                    synth,
                    bytes,
                ));
            }
        }
    }

    // .cursorrules / .windsurfrules (siblings of `.cursor`).
    if let Some(home_root) = cursor_root.parent() {
        for fname in [".cursorrules", ".windsurfrules"] {
            let p = home_root.join(fname);
            if p.is_file() {
                if let Ok(bytes) = std::fs::read(&p) {
                    let synth = format!("{agent_seg}/{fname}");
                    let name = fname.trim_start_matches('.');
                    out.push(single_file_cap(
                        agent.id,
                        CapKind::Rules,
                        name,
                        &p,
                        synth,
                        bytes,
                    ));
                }
            }
        }
    }
}

// ─── discovery: slash commands (→ skill) ─────────────────────────────────────

/// Slash commands map to the `skill` kind (the backend has no `command` kind, and
/// Claude treats commands + skills as the same mechanism). Claude `commands/*.md`
/// and Codex `prompts/*.md` synthesize a verbatim `SKILL.md`; Gemini
/// `commands/*.toml` extracts the `prompt` field into one.
fn discover_commands(
    agent: &DetectedAgent,
    out: &mut Vec<LocalCapability>,
    skips: &mut Vec<SkipNote>,
) {
    let Some(root) = agent.skill_dir.as_ref().and_then(|d| d.parent()) else {
        return;
    };
    let agent_seg = agent.id.as_str();
    match agent.id {
        AgentId::ClaudeCode => {
            scan_markdown_dir(
                &root.join("commands"),
                &format!("{agent_seg}/commands"),
                agent.id,
                out,
                skips,
            );
        }
        AgentId::Codex => {
            scan_markdown_dir(
                &root.join("prompts"),
                &format!("{agent_seg}/prompts"),
                agent.id,
                out,
                skips,
            );
        }
        AgentId::Gemini => {
            scan_toml_commands(
                &root.join("commands"),
                &format!("{agent_seg}/commands"),
                agent.id,
                out,
                skips,
            );
        }
        _ => {}
    }
}

// ─── discovery: subagents (Claude Code only, → skill) ────────────────────────

/// Claude subagents (`~/.claude/agents/*.md`) map to the `skill` kind — the
/// subagent markdown already carries `name:`/`description:` frontmatter the
/// backend reads, so it bundles verbatim.
fn discover_subagents(
    agent: &DetectedAgent,
    out: &mut Vec<LocalCapability>,
    skips: &mut Vec<SkipNote>,
) {
    if agent.id != AgentId::ClaudeCode {
        return;
    }
    let Some(root) = agent.skill_dir.as_ref().and_then(|d| d.parent()) else {
        return;
    };
    scan_markdown_dir(
        &root.join("agents"),
        &format!("{}/agents", agent.id.as_str()),
        agent.id,
        out,
        skips,
    );
}

/// Walk a directory of markdown prompt files (recursing namespaced subdirs); each
/// `*.md` becomes a synthetic [`CapKind::Skill`] whose `SKILL.md` body is the
/// markdown verbatim. A namespaced subpath (`lde/x.md`) maps to the colon-name
/// `lde:x`, injected as a `name:` frontmatter ONLY when the source carries no
/// `---` frontmatter of its own. Shared by Claude `commands/` + `agents/`, Codex
/// `prompts/`, and a plugin's bundled `commands/` + `agents/`.
fn scan_markdown_dir(
    dir: &Path,
    mount: &str,
    agent: AgentId,
    out: &mut Vec<LocalCapability>,
    skips: &mut Vec<SkipNote>,
) {
    if !dir.is_dir() {
        return;
    }
    let mut files: Vec<(String, PathBuf)> = Vec::new();
    collect_files_with_ext(dir, dir, "md", &mut files);
    files.sort();
    for (rel, path) in files {
        // rel like "lde/brainstorming.md" → stem path "lde/brainstorming".
        let stem = rel.strip_suffix(".md").unwrap_or(&rel);
        let name = stem.replace('/', ":");
        let cap_mount = format!("{mount}/{stem}");
        let anchor = format!("{cap_mount}/SKILL.md");
        let Some(raw) = read_capability_file(&path, &anchor, agent, skips) else {
            continue;
        };
        let body = synthesize_skill_md(&name, &raw);
        out.push(single_file_cap(
            agent,
            CapKind::Skill,
            &name,
            &path,
            anchor,
            body,
        ));
    }
}

/// Gemini `commands/*.toml`: parse with the `toml` crate, extract the `prompt`
/// field, and synthesize a `SKILL.md` whose body is that prose. Malformed TOML →
/// a [`SkipReason::MalformedConfig`]; a file with no `prompt` is silently ignored.
fn scan_toml_commands(
    dir: &Path,
    mount: &str,
    agent: AgentId,
    out: &mut Vec<LocalCapability>,
    skips: &mut Vec<SkipNote>,
) {
    if !dir.is_dir() {
        return;
    }
    let mut files: Vec<(String, PathBuf)> = Vec::new();
    collect_files_with_ext(dir, dir, "toml", &mut files);
    files.sort();
    for (rel, path) in files {
        let stem = rel.strip_suffix(".toml").unwrap_or(&rel);
        let name = stem.replace('/', ":");
        let cap_mount = format!("{mount}/{stem}");
        let anchor = format!("{cap_mount}/SKILL.md");
        let text = match std::fs::read_to_string(&path) {
            Ok(t) => t,
            Err(_) => {
                skips.push(SkipNote::at(agent, anchor, SkipReason::Unreadable));
                continue;
            }
        };
        let value: toml::Value = match toml::from_str(&text) {
            Ok(v) => v,
            Err(_) => {
                skips.push(SkipNote::at(agent, anchor, SkipReason::MalformedConfig));
                continue;
            }
        };
        let Some(prompt) = value.get("prompt").and_then(|p| p.as_str()) else {
            continue; // a TOML command without a prompt is not a scannable prompt
        };
        let body = format!("---\nname: {name}\n---\n{prompt}\n").into_bytes();
        out.push(single_file_cap(
            agent,
            CapKind::Skill,
            &name,
            &path,
            anchor,
            body,
        ));
    }
}

// ─── discovery: plugin cache (Claude Code only) ──────────────────────────────

/// Decompose the Claude plugin cache (`~/.claude/plugins/cache/<mp>/<plugin>/
/// <ver>/`). Only the installed-active version (per `installed_plugins.json`,
/// else the lexically-greatest version dir) is read; its bundled `skills/`,
/// `.mcp.json`, `hooks/`, `commands/`, `agents/`, and `.claude-plugin/plugin.json`
/// each become their own scored capability, mounted under
/// `claude-code/plugins/<mp>__<plugin>/`. Everything outside those capability
/// subdirs (`bin/`, `lib/`, `src/`, …) is ignored.
fn discover_plugins(
    agent: &DetectedAgent,
    out: &mut Vec<LocalCapability>,
    skips: &mut Vec<SkipNote>,
) {
    if agent.id != AgentId::ClaudeCode {
        return;
    }
    let Some(claude_root) = agent.skill_dir.as_ref().and_then(|d| d.parent()) else {
        return;
    };
    let plugins_root = claude_root.join("plugins");
    let cache = plugins_root.join("cache");
    if !cache.is_dir() {
        return;
    }
    let versions = active_plugin_versions(&plugins_root);

    let mut marketplaces: Vec<PathBuf> = match std::fs::read_dir(&cache) {
        Ok(rd) => rd.filter_map(|e| e.ok().map(|e| e.path())).collect(),
        Err(_) => return,
    };
    marketplaces.sort();
    for mp_dir in marketplaces {
        if !mp_dir.is_dir() {
            continue;
        }
        let mp = mp_dir
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("")
            .to_string();
        let mut plugin_dirs: Vec<PathBuf> = match std::fs::read_dir(&mp_dir) {
            Ok(rd) => rd.filter_map(|e| e.ok().map(|e| e.path())).collect(),
            Err(_) => continue,
        };
        plugin_dirs.sort();
        for plugin_dir in plugin_dirs {
            if !plugin_dir.is_dir() {
                continue;
            }
            let plugin = plugin_dir
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("")
                .to_string();
            let Some(version) = versions
                .get(&(mp.clone(), plugin.clone()))
                .filter(|v| plugin_dir.join(v).is_dir())
                .cloned()
                .or_else(|| greatest_version_dir(&plugin_dir))
            else {
                continue; // no resolvable version dir
            };
            let pdir = plugin_dir.join(&version);
            let mount = format!(
                "{}/plugins/{}__{}",
                agent.id.as_str(),
                sanitize_segment(&mp),
                sanitize_segment(&plugin)
            );
            scan_skills_dir(
                &pdir.join("skills"),
                &format!("{mount}/skills"),
                agent.id,
                out,
                skips,
            );
            scan_markdown_dir(
                &pdir.join("commands"),
                &format!("{mount}/commands"),
                agent.id,
                out,
                skips,
            );
            scan_markdown_dir(
                &pdir.join("agents"),
                &format!("{mount}/agents"),
                agent.id,
                out,
                skips,
            );
            scan_hooks_dir(
                &pdir.join("hooks"),
                &format!("{mount}/hooks"),
                agent.id,
                out,
                skips,
            );
            scan_mcp_file(
                &pdir.join(".mcp.json"),
                &["mcpServers"],
                &format!("{mount}/mcp"),
                agent.id,
                out,
                skips,
            );
            scan_plugin_manifest(&pdir, &mount, agent.id, out, skips);
        }
    }
}

/// Map `(marketplace, plugin) → active-version dir name` from
/// `plugins/installed_plugins.json` (key `<plugin>@<marketplace>` → installs[]).
/// Prefers the `user`-scope install (a global audit), else the first entry. An
/// unreadable/absent ledger yields an empty map (the caller falls back to the
/// greatest version dir).
fn active_plugin_versions(
    plugins_root: &Path,
) -> std::collections::HashMap<(String, String), String> {
    let mut map = std::collections::HashMap::new();
    let file = plugins_root.join("installed_plugins.json");
    let Ok(text) = std::fs::read_to_string(&file) else {
        return map;
    };
    let Some(value) = parse_jsonc(&text) else {
        return map;
    };
    let Some(plugins) = value.get("plugins").and_then(|p| p.as_object()) else {
        return map;
    };
    for (key, installs) in plugins {
        let Some((plugin, mp)) = key.rsplit_once('@') else {
            continue;
        };
        let Some(arr) = installs.as_array() else {
            continue;
        };
        let chosen = arr
            .iter()
            .find(|e| e.get("scope").and_then(|s| s.as_str()) == Some("user"))
            .or_else(|| arr.first());
        if let Some(version) = chosen
            .and_then(|e| e.get("version"))
            .and_then(|v| v.as_str())
        {
            map.insert((mp.to_string(), plugin.to_string()), version.to_string());
        }
    }
    map
}

/// The lexically-greatest immediate child directory name of `dir`, if any — the
/// version-selection fallback when `installed_plugins.json` has no entry.
fn greatest_version_dir(dir: &Path) -> Option<String> {
    let mut best: Option<String> = None;
    for entry in std::fs::read_dir(dir).ok()?.flatten() {
        if entry.path().is_dir() {
            if let Some(name) = entry.file_name().to_str() {
                if best.as_deref().is_none_or(|b| name > b) {
                    best = Some(name.to_string());
                }
            }
        }
    }
    best
}

/// Emit one [`CapKind::Plugin`] capability for a plugin's `.claude-plugin/
/// plugin.json` manifest (the 5 `SS-PLUGIN-*` rules fire on it). Entries are the
/// `.claude-plugin/**` tree (the anchor) plus top-level loose text files
/// (`README.md`, `LICENSE`, …) — capability subdirs (`skills/`, `bin/`, `lib/`,
/// …) are scanned separately or ignored, keeping mega-plugins tight.
fn scan_plugin_manifest(
    plugin_dir: &Path,
    mount: &str,
    agent: AgentId,
    out: &mut Vec<LocalCapability>,
    skips: &mut Vec<SkipNote>,
) {
    let manifest_dir = plugin_dir.join(".claude-plugin");
    if !manifest_dir.join("plugin.json").is_file() {
        return; // not a plugin manifest tree
    }
    let anchor = format!("{mount}/.claude-plugin/plugin.json");
    let mut entries: Vec<(String, Vec<u8>)> = Vec::new();
    // The manifest tree (`.claude-plugin/**`) — `plugin.json` is the anchor.
    walk_dir(
        &manifest_dir,
        &manifest_dir,
        &format!("{mount}/.claude-plugin"),
        "plugin.json",
        agent,
        &mut entries,
        skips,
    );
    // Top-level loose text files (README / LICENSE / …) — non-recursive, so the
    // capability subdirs are left to their own scanners.
    if let Ok(rd) = std::fs::read_dir(plugin_dir) {
        let mut files: Vec<PathBuf> = rd.filter_map(|e| e.ok().map(|e| e.path())).collect();
        files.sort();
        for path in files {
            if !path.is_file() {
                continue;
            }
            let fname = path.file_name().and_then(|n| n.to_str()).unwrap_or("");
            let synth = format!("{mount}/{fname}");
            if let Some(bytes) = read_capability_file(&path, &synth, agent, skips) {
                entries.push((synth, bytes));
            }
        }
    }
    if entries.iter().all(|(p, _)| p != &anchor) {
        return; // the manifest itself was unreadable → can't be detected
    }
    let name = plugin_dir
        .parent()
        .and_then(|p| p.file_name())
        .and_then(|n| n.to_str())
        .unwrap_or("plugin")
        .to_string();
    let (entries, bytes) = apply_cap_budget(agent, &anchor, entries, skips);
    out.push(LocalCapability {
        agent,
        kind: CapKind::Plugin,
        name,
        origin: plugin_dir.to_path_buf(),
        anchor,
        entries,
        bytes,
    });
}

/// Recursively collect `(rel_posix, abs_path)` for every file with extension
/// `ext` under `dir`, skipping excluded (vendor/build/lock) directories.
fn collect_files_with_ext(root: &Path, dir: &Path, ext: &str, out: &mut Vec<(String, PathBuf)>) {
    let Ok(rd) = std::fs::read_dir(dir) else {
        return;
    };
    let mut paths: Vec<PathBuf> = rd.filter_map(|e| e.ok().map(|e| e.path())).collect();
    paths.sort();
    for path in paths {
        let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("");
        if path.is_dir() {
            if !is_excluded_dir(name) {
                collect_files_with_ext(root, &path, ext, out);
            }
        } else if path.is_file() && ext_of(name).as_deref() == Some(ext) {
            out.push((rel_posix(root, &path), path));
        }
    }
}

/// Wrap a markdown body in a `name:` frontmatter when it carries none of its own;
/// a body that already starts with `---` frontmatter is returned verbatim.
fn synthesize_skill_md(name: &str, raw: &[u8]) -> Vec<u8> {
    if String::from_utf8_lossy(raw).trim_start().starts_with("---") {
        return raw.to_vec();
    }
    let mut body = format!("---\nname: {name}\n---\n").into_bytes();
    body.extend_from_slice(raw);
    body
}

// ─── capability builders ─────────────────────────────────────────────────────

/// A single-file capability (hook / rules) — the file IS the anchor, always kept.
fn single_file_cap(
    agent: AgentId,
    kind: CapKind,
    name: &str,
    origin: &Path,
    synth: String,
    bytes: Vec<u8>,
) -> LocalCapability {
    let len = bytes.len();
    LocalCapability {
        agent,
        kind,
        name: name.to_string(),
        origin: origin.to_path_buf(),
        anchor: synth.clone(),
        entries: vec![(synth, bytes)],
        bytes: len,
    }
}

/// Walk a capability directory (skill), apply per-file + per-cap filters, and
/// build the [`LocalCapability`]. Returns `None` if even the anchor is gone.
fn collect_dir_capability(
    agent: AgentId,
    kind: CapKind,
    name: &str,
    origin: &Path,
    mount: &str,
    anchor: &str,
    skips: &mut Vec<SkipNote>,
) -> Option<LocalCapability> {
    let anchor_rel = anchor.strip_prefix(&format!("{mount}/")).unwrap_or("");
    let mut entries: Vec<(String, Vec<u8>)> = Vec::new();
    walk_dir(
        origin,
        origin,
        mount,
        anchor_rel,
        agent,
        &mut entries,
        skips,
    );
    if entries.iter().all(|(p, _)| p != anchor) {
        // The anchor itself was unreadable → can't be detected; drop the cap.
        return None;
    }
    let (entries, bytes) = apply_cap_budget(agent, anchor, entries, skips);
    Some(LocalCapability {
        agent,
        kind,
        name: name.to_string(),
        origin: origin.to_path_buf(),
        anchor: anchor.to_string(),
        entries,
        bytes,
    })
}

#[allow(clippy::too_many_arguments)]
fn walk_dir(
    root: &Path,
    dir: &Path,
    mount: &str,
    anchor_rel: &str,
    agent: AgentId,
    entries: &mut Vec<(String, Vec<u8>)>,
    skips: &mut Vec<SkipNote>,
) {
    let mut paths: Vec<PathBuf> = match std::fs::read_dir(dir) {
        Ok(rd) => rd.filter_map(|e| e.ok().map(|e| e.path())).collect(),
        Err(_) => {
            skips.push(SkipNote::at(
                agent,
                dir.to_string_lossy(),
                SkipReason::Unreadable,
            ));
            return;
        }
    };
    paths.sort();
    for path in paths {
        let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("");
        if path.is_dir() {
            if is_excluded_dir(name) {
                skips.push(SkipNote::at(
                    agent,
                    rel_posix(root, &path),
                    SkipReason::VendorDir,
                ));
                continue;
            }
            walk_dir(root, &path, mount, anchor_rel, agent, entries, skips);
        } else if path.is_file() {
            let rel = rel_posix(root, &path);
            let synth = format!("{mount}/{rel}");
            if rel == anchor_rel {
                // The anchor is always kept, unfiltered (it is what the backend
                // needs to detect the capability).
                match std::fs::read(&path) {
                    Ok(bytes) => entries.push((synth, bytes)),
                    Err(_) => skips.push(SkipNote::at(agent, synth, SkipReason::Unreadable)),
                }
            } else if let Some(bytes) = read_capability_file(&path, &synth, agent, skips) {
                entries.push((synth, bytes));
            }
        }
    }
}

/// Read a non-anchor capability file, applying the per-file ext / size / binary
/// filters. Returns the bytes to bundle, or `None` (with a [`SkipNote`] recorded)
/// when the file is excluded.
fn read_capability_file(
    path: &Path,
    synth: &str,
    agent: AgentId,
    skips: &mut Vec<SkipNote>,
) -> Option<Vec<u8>> {
    if let Some(reason) = excluded_ext_reason(synth) {
        skips.push(SkipNote::at(agent, synth.to_string(), reason));
        return None;
    }
    if let Ok(meta) = std::fs::metadata(path) {
        if meta.len() as usize > budget::MAX_FILE_BYTES {
            skips.push(SkipNote::at(
                agent,
                synth.to_string(),
                SkipReason::TooLargeFile,
            ));
            return None;
        }
    }
    let bytes = match std::fs::read(path) {
        Ok(b) => b,
        Err(_) => {
            skips.push(SkipNote::at(
                agent,
                synth.to_string(),
                SkipReason::Unreadable,
            ));
            return None;
        }
    };
    if looks_binary(&bytes) {
        skips.push(SkipNote::at(agent, synth.to_string(), SkipReason::Binary));
        return None;
    }
    Some(bytes)
}

/// Trim a capability to `MAX_CAPABILITY_BYTES`, always keeping the anchor and
/// dropping the largest non-anchor files first (each → a `CapTooLarge` skip).
fn apply_cap_budget(
    agent: AgentId,
    anchor: &str,
    entries: Vec<(String, Vec<u8>)>,
    skips: &mut Vec<SkipNote>,
) -> (Vec<(String, Vec<u8>)>, usize) {
    let total: usize = entries.iter().map(|(_, b)| b.len()).sum();
    if total <= budget::MAX_CAPABILITY_BYTES {
        return (entries, total);
    }
    let mut keep: Vec<(String, Vec<u8>)> = Vec::new();
    let mut others: Vec<(String, Vec<u8>)> = Vec::new();
    for (p, b) in entries {
        if p == anchor {
            keep.push((p, b));
        } else {
            others.push((p, b));
        }
    }
    // Keep smallest non-anchor files first; drop the largest that don't fit.
    others.sort_by_key(|a| a.1.len());
    let mut cur: usize = keep.iter().map(|(_, b)| b.len()).sum();
    for (p, b) in others {
        if cur + b.len() <= budget::MAX_CAPABILITY_BYTES {
            cur += b.len();
            keep.push((p, b));
        } else {
            skips.push(SkipNote::at(agent, p, SkipReason::CapTooLarge));
        }
    }
    (keep, cur)
}

// ─── global budget + casefold guard (used by the bundle builder) ─────────────

/// Select capabilities into the total budget, priority-ordered. A cap that
/// overflows the total-bytes / entry budget is dropped whole (`BudgetFull`).
pub fn select_within_budget(
    mut caps: Vec<LocalCapability>,
) -> (Vec<LocalCapability>, Vec<SkipNote>) {
    caps.sort_by(|a, b| {
        a.kind
            .priority()
            .cmp(&b.kind.priority())
            .then_with(|| a.name.cmp(&b.name))
            .then_with(|| a.anchor.cmp(&b.anchor))
    });
    let mut kept = Vec::new();
    let mut skips = Vec::new();
    let mut total_bytes = 0usize;
    let mut total_entries = 0usize;
    for cap in caps {
        if total_bytes + cap.bytes <= budget::MAX_TOTAL_BYTES
            && total_entries + cap.entries.len() <= budget::MAX_ENTRIES
        {
            total_bytes += cap.bytes;
            total_entries += cap.entries.len();
            kept.push(cap);
        } else {
            skips.push(SkipNote::at(
                cap.agent,
                cap.anchor.clone(),
                SkipReason::BudgetFull,
            ));
        }
    }
    (kept, skips)
}

/// Drop any later entry whose rel-path casefold-collides with an earlier one
/// (would otherwise trip the upload `dup_path` guard on a case-insensitive FS).
/// Returns the kept entries + the dropped paths.
pub fn casefold_dedup(entries: Vec<(String, Vec<u8>)>) -> (Vec<(String, Vec<u8>)>, Vec<String>) {
    let mut seen: HashSet<String> = HashSet::new();
    let mut kept = Vec::new();
    let mut dropped = Vec::new();
    for (p, b) in entries {
        if seen.insert(p.to_lowercase()) {
            kept.push((p, b));
        } else {
            dropped.push(p);
        }
    }
    (kept, dropped)
}

// ─── small path helpers ──────────────────────────────────────────────────────

fn rel_posix(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .components()
        .map(|c| c.as_os_str().to_string_lossy().into_owned())
        .collect::<Vec<_>>()
        .join("/")
}

/// Make a server name safe as a single path segment, keeping the real name for
/// the JSON `name` field. Empty/degenerate → `item`.
fn sanitize_segment(s: &str) -> String {
    let cleaned: String = s
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.' {
                c
            } else {
                '-'
            }
        })
        .collect();
    let trimmed = cleaned.trim_matches(['.', '-', '_']);
    if trimmed.is_empty() {
        "item".to_string()
    } else {
        trimmed.to_string()
    }
}

fn parse_jsonc(text: &str) -> Option<Value> {
    jsonc_parser::parse_to_serde_value(text, &jsonc_parser::ParseOptions::default())
        .ok()
        .flatten()
}

/// Navigate `value` down `key_path` and return the final object as a map.
fn navigate_object<'a>(
    value: &'a Value,
    key_path: &[&str],
) -> Option<&'a serde_json::Map<String, Value>> {
    let mut cur = value;
    for seg in key_path {
        cur = cur.get(seg)?;
    }
    cur.as_object()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn agent(id: AgentId, mcp: PathBuf, skill: Option<PathBuf>) -> DetectedAgent {
        DetectedAgent {
            id,
            version: None,
            mcp_config_path: mcp,
            skill_dir: skill,
            rules_dir: None,
            hooks_path: None,
            plugin_dir: None,
            scope: Scope::Global,
        }
    }

    fn literal_cap(entries: Vec<(&str, &[u8])>) -> LocalCapability {
        let entries: Vec<(String, Vec<u8>)> = entries
            .into_iter()
            .map(|(p, b)| (p.to_string(), b.to_vec()))
            .collect();
        let bytes = entries.iter().map(|(_, b)| b.len()).sum();
        LocalCapability {
            agent: AgentId::ClaudeCode,
            kind: CapKind::Skill,
            name: "x".into(),
            origin: PathBuf::from("/x"),
            anchor: entries.first().map(|(p, _)| p.clone()).unwrap_or_default(),
            entries,
            bytes,
        }
    }

    #[test]
    fn content_hash_is_stable_and_order_independent() {
        let a = literal_cap(vec![
            ("a/SKILL.md", b"---\nname: x\n---\n"),
            ("a/run.py", b"hi"),
        ]);
        let b = literal_cap(vec![
            ("a/run.py", b"hi"),
            ("a/SKILL.md", b"---\nname: x\n---\n"),
        ]);
        assert_eq!(a.content_hash(), a.content_hash(), "stable across calls");
        assert_eq!(
            a.content_hash(),
            b.content_hash(),
            "entry order independent"
        );
        assert_eq!(a.content_hash().len(), 64, "hex sha256");
    }

    #[test]
    fn content_hash_changes_when_bytes_change() {
        let a = literal_cap(vec![("a/SKILL.md", b"original")]);
        let b = literal_cap(vec![("a/SKILL.md", b"edited!!")]);
        assert_ne!(a.content_hash(), b.content_hash());
    }

    #[test]
    fn skill_discovered_with_exact_relpath() {
        let tmp = tempfile::tempdir().unwrap();
        let skills = tmp.path().join(".claude").join("skills");
        fs::create_dir_all(skills.join("pdf-extract")).unwrap();
        fs::write(
            skills.join("pdf-extract").join("SKILL.md"),
            b"---\nname: pdf-extract\n---\n# pdf",
        )
        .unwrap();
        fs::write(skills.join("pdf-extract").join("run.py"), b"print('hi')\n").unwrap();

        let a = agent(
            AgentId::ClaudeCode,
            tmp.path().join(".claude.json"),
            Some(skills),
        );
        let enm = enumerate_from(&[a]);
        let cap = enm
            .capabilities
            .iter()
            .find(|c| c.kind == CapKind::Skill)
            .expect("skill discovered");
        assert_eq!(cap.name, "pdf-extract");
        assert_eq!(cap.anchor, "claude-code/skills/pdf-extract/SKILL.md");
        assert!(cap
            .entries
            .iter()
            .any(|(p, _)| p == "claude-code/skills/pdf-extract/SKILL.md"));
        assert!(cap
            .entries
            .iter()
            .any(|(p, _)| p == "claude-code/skills/pdf-extract/run.py"));
    }

    #[test]
    fn mcp_json_extracted_per_server() {
        let tmp = tempfile::tempdir().unwrap();
        let cfg = tmp.path().join(".cursor").join("mcp.json");
        fs::create_dir_all(cfg.parent().unwrap()).unwrap();
        fs::write(
            &cfg,
            r#"{ "mcpServers": { "github": { "command": "npx", "args": ["-y", "gh"] } } }"#,
        )
        .unwrap();

        let a = agent(AgentId::Cursor, cfg, None);
        let enm = enumerate_from(&[a]);
        let cap = enm
            .capabilities
            .iter()
            .find(|c| c.kind == CapKind::McpServer)
            .expect("mcp discovered");
        assert_eq!(cap.name, "github");
        assert_eq!(cap.anchor, "cursor/mcp/github/mcp.json");
        let (_, body) = &cap.entries[0];
        let v: Value = serde_json::from_slice(body).unwrap();
        assert_eq!(v["name"], "github");
        assert_eq!(v["server"]["command"], "npx");
    }

    #[test]
    fn codex_toml_mcp_extracted() {
        let tmp = tempfile::tempdir().unwrap();
        let cfg = tmp.path().join(".codex").join("config.toml");
        fs::create_dir_all(cfg.parent().unwrap()).unwrap();
        fs::write(
            &cfg,
            "model = \"o3\"\n\n[mcp_servers.fs]\ncommand = \"npx\"\n",
        )
        .unwrap();

        let a = agent(
            AgentId::Codex,
            cfg.clone(),
            Some(tmp.path().join(".codex").join("skills")),
        );
        let enm = enumerate_from(&[a]);
        let cap = enm
            .capabilities
            .iter()
            .find(|c| c.kind == CapKind::McpServer)
            .expect("codex mcp discovered");
        assert_eq!(cap.name, "fs");
        let v: Value = serde_json::from_slice(&cap.entries[0].1).unwrap();
        assert_eq!(v["server"]["command"], "npx");
    }

    #[test]
    fn copilot_vscode_uses_servers_key() {
        let tmp = tempfile::tempdir().unwrap();
        let cfg = tmp.path().join(".vscode").join("mcp.json");
        fs::create_dir_all(cfg.parent().unwrap()).unwrap();
        fs::write(&cfg, r#"{ "servers": { "db": { "url": "http://x" } } }"#).unwrap();

        let a = agent(AgentId::Copilot, cfg, None);
        let enm = enumerate_from(&[a]);
        assert!(enm
            .capabilities
            .iter()
            .any(|c| c.kind == CapKind::McpServer && c.name == "db"));
    }

    #[test]
    fn openclaw_nested_key_probed() {
        let tmp = tempfile::tempdir().unwrap();
        let cfg = tmp.path().join(".openclaw").join("openclaw.json");
        fs::create_dir_all(cfg.parent().unwrap()).unwrap();
        fs::write(
            &cfg,
            r#"{ "mcp": { "servers": { "n": { "url": "http://x" } } } }"#,
        )
        .unwrap();

        let a = agent(AgentId::Openclaw, cfg, None);
        let enm = enumerate_from(&[a]);
        assert!(enm
            .capabilities
            .iter()
            .any(|c| c.kind == CapKind::McpServer && c.name == "n"));
    }

    #[test]
    fn cursor_mdc_rules_discovered() {
        let tmp = tempfile::tempdir().unwrap();
        let cfg = tmp.path().join(".cursor").join("mcp.json");
        fs::create_dir_all(tmp.path().join(".cursor").join("rules")).unwrap();
        fs::write(&cfg, "{}").unwrap();
        fs::write(
            tmp.path().join(".cursor").join("rules").join("style.mdc"),
            b"---\nrule\n---\n",
        )
        .unwrap();

        let a = agent(AgentId::Cursor, cfg, None);
        let enm = enumerate_from(&[a]);
        let cap = enm
            .capabilities
            .iter()
            .find(|c| c.kind == CapKind::Rules)
            .expect("rules discovered");
        assert_eq!(cap.anchor, "cursor/.cursor/rules/style.mdc");
    }

    #[test]
    fn claude_hooks_discovered() {
        let tmp = tempfile::tempdir().unwrap();
        let claude = tmp.path().join(".claude");
        fs::create_dir_all(claude.join("hooks")).unwrap();
        fs::write(
            claude.join("settings.json"),
            r#"{ "hooks": { "PreToolUse": [] } }"#,
        )
        .unwrap();
        fs::write(
            claude.join("hooks").join("pre-commit.json"),
            r#"{ "command": "x" }"#,
        )
        .unwrap();

        let a = agent(
            AgentId::ClaudeCode,
            tmp.path().join(".claude.json"),
            Some(claude.join("skills")),
        );
        let enm = enumerate_from(&[a]);
        assert!(enm
            .capabilities
            .iter()
            .any(|c| c.kind == CapKind::Hook && c.anchor == "claude-code/.claude/settings.json"));
        assert!(enm
            .capabilities
            .iter()
            .any(|c| c.kind == CapKind::Hook && c.anchor == "claude-code/hooks/pre-commit.json"));
    }

    #[test]
    fn oversized_and_binary_files_skipped_anchor_kept() {
        let tmp = tempfile::tempdir().unwrap();
        let skills = tmp.path().join(".claude").join("skills");
        fs::create_dir_all(skills.join("big")).unwrap();
        fs::write(
            skills.join("big").join("SKILL.md"),
            b"---\nname: big\n---\n",
        )
        .unwrap();
        // Binary file (NUL bytes).
        fs::write(skills.join("big").join("blob.dat"), [0u8, 1, 2, 0, 3]).unwrap();
        // Oversized text file (> 1 MiB).
        fs::write(
            skills.join("big").join("huge.txt"),
            vec![b'a'; budget::MAX_FILE_BYTES + 1],
        )
        .unwrap();
        // Nested archive.
        fs::write(skills.join("big").join("bundle.zip"), b"PK\x03\x04").unwrap();

        let a = agent(
            AgentId::ClaudeCode,
            tmp.path().join(".claude.json"),
            Some(skills),
        );
        let enm = enumerate_from(&[a]);
        let cap = enm.capabilities.iter().find(|c| c.name == "big").unwrap();
        assert!(cap.entries.iter().any(|(p, _)| p.ends_with("SKILL.md")));
        assert!(!cap.entries.iter().any(|(p, _)| p.ends_with("blob.dat")));
        assert!(!cap.entries.iter().any(|(p, _)| p.ends_with("huge.txt")));
        assert!(!cap.entries.iter().any(|(p, _)| p.ends_with("bundle.zip")));
        // The skips record each reason.
        assert!(enm.skips.iter().any(|s| s.reason == SkipReason::Binary));
        assert!(enm
            .skips
            .iter()
            .any(|s| s.reason == SkipReason::TooLargeFile));
        assert!(enm
            .skips
            .iter()
            .any(|s| s.reason == SkipReason::NestedArchive));
    }

    #[test]
    fn vendor_dirs_excluded() {
        let tmp = tempfile::tempdir().unwrap();
        let skills = tmp.path().join(".claude").join("skills");
        fs::create_dir_all(skills.join("s").join("node_modules").join("pkg")).unwrap();
        fs::write(skills.join("s").join("SKILL.md"), b"---\nname: s\n---\n").unwrap();
        fs::write(
            skills
                .join("s")
                .join("node_modules")
                .join("pkg")
                .join("index.js"),
            b"x",
        )
        .unwrap();

        let a = agent(
            AgentId::ClaudeCode,
            tmp.path().join(".claude.json"),
            Some(skills),
        );
        let enm = enumerate_from(&[a]);
        let cap = enm.capabilities.iter().find(|c| c.name == "s").unwrap();
        assert!(!cap.entries.iter().any(|(p, _)| p.contains("node_modules")));
        assert!(enm.skips.iter().any(|s| s.reason == SkipReason::VendorDir));
    }

    #[test]
    fn malformed_config_is_skip_not_error() {
        let tmp = tempfile::tempdir().unwrap();
        let cfg = tmp.path().join(".cursor").join("mcp.json");
        fs::create_dir_all(cfg.parent().unwrap()).unwrap();
        fs::write(&cfg, "{ this is not json").unwrap();

        let a = agent(AgentId::Cursor, cfg, None);
        let enm = enumerate_from(&[a]);
        assert!(enm.capabilities.is_empty());
        assert!(enm
            .skips
            .iter()
            .any(|s| s.reason == SkipReason::MalformedConfig));
    }

    #[test]
    fn cross_agent_names_do_not_collide() {
        let tmp = tempfile::tempdir().unwrap();
        let claude_skills = tmp.path().join(".claude").join("skills");
        let codex_skills = tmp.path().join(".codex").join("skills");
        for s in [&claude_skills, &codex_skills] {
            fs::create_dir_all(s.join("shared")).unwrap();
            fs::write(
                s.join("shared").join("SKILL.md"),
                b"---\nname: shared\n---\n",
            )
            .unwrap();
        }
        let a1 = agent(
            AgentId::ClaudeCode,
            tmp.path().join(".claude.json"),
            Some(claude_skills),
        );
        let a2 = agent(
            AgentId::Codex,
            tmp.path().join(".codex").join("config.toml"),
            Some(codex_skills),
        );
        let enm = enumerate_from(&[a1, a2]);
        let anchors: Vec<&str> = enm.capabilities.iter().map(|c| c.anchor.as_str()).collect();
        assert!(anchors.contains(&"claude-code/skills/shared/SKILL.md"));
        assert!(anchors.contains(&"codex/skills/shared/SKILL.md"));
    }

    #[test]
    fn select_within_budget_priority_and_overflow() {
        let cap = |kind: CapKind, name: &str, bytes: usize| LocalCapability {
            agent: AgentId::ClaudeCode,
            kind,
            name: name.to_string(),
            origin: PathBuf::new(),
            anchor: format!("a/{name}"),
            entries: vec![(format!("a/{name}"), vec![0u8; bytes])],
            bytes,
        };
        // Two caps; total budget only fits one. mcp_server (priority 0) wins.
        let big = budget::MAX_TOTAL_BYTES;
        let (kept, skips) = select_within_budget(vec![
            cap(CapKind::Skill, "s", big),
            cap(CapKind::McpServer, "m", big),
        ]);
        assert_eq!(kept.len(), 1);
        assert_eq!(kept[0].kind, CapKind::McpServer);
        assert_eq!(skips.len(), 1);
        assert_eq!(skips[0].reason, SkipReason::BudgetFull);
    }

    #[test]
    fn casefold_dedup_drops_collisions() {
        let (kept, dropped) = casefold_dedup(vec![
            ("a/X.md".to_string(), vec![1]),
            ("a/x.md".to_string(), vec![2]),
            ("a/y.md".to_string(), vec![3]),
        ]);
        assert_eq!(kept.len(), 2);
        assert_eq!(dropped, vec!["a/x.md".to_string()]);
    }

    /// A Claude agent rooted at `<tmp>/.claude` (skills dir parent = the config
    /// root the command/subagent/plugin discoverers derive their dirs from).
    fn claude_agent(tmp: &Path) -> DetectedAgent {
        agent(
            AgentId::ClaudeCode,
            tmp.join(".claude.json"),
            Some(tmp.join(".claude").join("skills")),
        )
    }

    #[test]
    fn commands_mapped_to_skill() {
        let tmp = tempfile::tempdir().unwrap();
        let cmds = tmp.path().join(".claude").join("commands").join("lde");
        fs::create_dir_all(&cmds).unwrap();
        fs::write(
            cmds.join("brainstorming.md"),
            b"# Brainstorm\nDo the thing.\n",
        )
        .unwrap();

        let enm = enumerate_from(&[claude_agent(tmp.path())]);
        let cap = enm
            .capabilities
            .iter()
            .find(|c| c.anchor == "claude-code/commands/lde/brainstorming/SKILL.md")
            .expect("namespaced command mapped to a skill anchor");
        assert_eq!(cap.kind, CapKind::Skill);
        assert_eq!(cap.name, "lde:brainstorming");
        // Body carries the command markdown (with a synthesized name frontmatter,
        // since the source had none).
        let body = String::from_utf8_lossy(&cap.entries[0].1);
        assert!(body.contains("Do the thing."));
        assert!(body.contains("name: lde:brainstorming"));
    }

    #[test]
    fn subagents_mapped_to_skill() {
        let tmp = tempfile::tempdir().unwrap();
        let agents = tmp.path().join(".claude").join("agents");
        fs::create_dir_all(&agents).unwrap();
        fs::write(
            agents.join("senior-qa-tester.md"),
            b"---\nname: senior-qa-tester\ndescription: QA\n---\nBody.\n",
        )
        .unwrap();

        let enm = enumerate_from(&[claude_agent(tmp.path())]);
        let cap = enm
            .capabilities
            .iter()
            .find(|c| c.anchor == "claude-code/agents/senior-qa-tester/SKILL.md")
            .expect("subagent mapped to a skill anchor");
        assert_eq!(cap.kind, CapKind::Skill);
        // The source frontmatter `name:` is preserved verbatim (not re-synthesized).
        let body = String::from_utf8_lossy(&cap.entries[0].1);
        assert!(body.starts_with("---\nname: senior-qa-tester"));
        assert!(body.contains("Body."));
    }

    #[test]
    fn codex_prompts_mapped_to_skill() {
        let tmp = tempfile::tempdir().unwrap();
        let prompts = tmp.path().join(".codex").join("prompts");
        fs::create_dir_all(&prompts).unwrap();
        fs::write(prompts.join("refactor.md"), b"Refactor it.\n").unwrap();

        let a = agent(
            AgentId::Codex,
            tmp.path().join(".codex").join("config.toml"),
            Some(tmp.path().join(".codex").join("skills")),
        );
        let enm = enumerate_from(&[a]);
        assert!(enm
            .capabilities
            .iter()
            .any(|c| c.kind == CapKind::Skill && c.anchor == "codex/prompts/refactor/SKILL.md"));
    }

    #[test]
    fn gemini_toml_command_prompt_extracted() {
        let tmp = tempfile::tempdir().unwrap();
        let cmds = tmp.path().join(".gemini").join("commands");
        fs::create_dir_all(&cmds).unwrap();
        fs::write(
            cmds.join("commit.toml"),
            b"description = \"git commit\"\nprompt = \"Write a commit message.\"\n",
        )
        .unwrap();
        fs::write(cmds.join("broken.toml"), b"this is = not [valid toml").unwrap();

        let a = agent(
            AgentId::Gemini,
            tmp.path().join(".gemini").join("settings.json"),
            Some(tmp.path().join(".gemini").join("skills")),
        );
        let enm = enumerate_from(&[a]);
        let cap = enm
            .capabilities
            .iter()
            .find(|c| c.anchor == "gemini/commands/commit/SKILL.md")
            .expect("toml command prompt extracted to a skill");
        assert_eq!(cap.kind, CapKind::Skill);
        let body = String::from_utf8_lossy(&cap.entries[0].1);
        assert!(body.contains("Write a commit message."));
        // The malformed TOML is a skip, never a hard error.
        assert!(enm
            .skips
            .iter()
            .any(|s| s.reason == SkipReason::MalformedConfig));
    }

    /// Build a Claude plugin-cache version dir at
    /// `<tmp>/.claude/plugins/cache/<mp>/<plugin>/<ver>/` and return it.
    fn plugin_version_dir(tmp: &Path, mp: &str, plugin: &str, ver: &str) -> PathBuf {
        let dir = tmp
            .join(".claude")
            .join("plugins")
            .join("cache")
            .join(mp)
            .join(plugin)
            .join(ver);
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn plugin_cache_decomposes_nested_caps() {
        let tmp = tempfile::tempdir().unwrap();
        let p = plugin_version_dir(tmp.path(), "mp", "p", "1.0.0");
        // skills/a/SKILL.md
        fs::create_dir_all(p.join("skills").join("a")).unwrap();
        fs::write(
            p.join("skills").join("a").join("SKILL.md"),
            b"---\nname: a\n---\n",
        )
        .unwrap();
        // .mcp.json
        fs::write(
            p.join(".mcp.json"),
            br#"{ "mcpServers": { "srv": { "command": "npx" } } }"#,
        )
        .unwrap();
        // hooks/h.json
        fs::create_dir_all(p.join("hooks")).unwrap();
        fs::write(p.join("hooks").join("h.json"), br#"{ "command": "x" }"#).unwrap();
        // .claude-plugin/plugin.json
        fs::create_dir_all(p.join(".claude-plugin")).unwrap();
        fs::write(
            p.join(".claude-plugin").join("plugin.json"),
            br#"{ "name": "p" }"#,
        )
        .unwrap();

        let enm = enumerate_from(&[claude_agent(tmp.path())]);
        let anchors: Vec<&str> = enm.capabilities.iter().map(|c| c.anchor.as_str()).collect();
        assert!(anchors.contains(&"claude-code/plugins/mp__p/skills/a/SKILL.md"));
        assert!(anchors.contains(&"claude-code/plugins/mp__p/mcp/srv/mcp.json"));
        assert!(anchors.contains(&"claude-code/plugins/mp__p/hooks/h.json"));
        assert!(anchors.contains(&"claude-code/plugins/mp__p/.claude-plugin/plugin.json"));
        // One of each kind from the single bundle.
        assert_eq!(
            enm.capabilities
                .iter()
                .filter(|c| c.kind == CapKind::Skill)
                .count(),
            1
        );
        assert!(enm
            .capabilities
            .iter()
            .any(|c| c.kind == CapKind::McpServer));
        assert!(enm.capabilities.iter().any(|c| c.kind == CapKind::Hook));
        let plugin_cap = enm
            .capabilities
            .iter()
            .find(|c| c.kind == CapKind::Plugin)
            .expect("plugin manifest cap");
        assert_eq!(plugin_cap.name, "p");
    }

    #[test]
    fn plugin_active_version_only() {
        let tmp = tempfile::tempdir().unwrap();
        // Two versions on disk, no installed_plugins.json → the lexically-greatest
        // (2.0.1) is the active one; 2.0.0 is never scanned.
        let old = plugin_version_dir(tmp.path(), "mp", "p", "2.0.0");
        fs::create_dir_all(old.join("skills").join("old")).unwrap();
        fs::write(
            old.join("skills").join("old").join("SKILL.md"),
            b"---\nname: old\n---\n",
        )
        .unwrap();
        let new = plugin_version_dir(tmp.path(), "mp", "p", "2.0.1");
        fs::create_dir_all(new.join("skills").join("new")).unwrap();
        fs::write(
            new.join("skills").join("new").join("SKILL.md"),
            b"---\nname: new\n---\n",
        )
        .unwrap();

        let enm = enumerate_from(&[claude_agent(tmp.path())]);
        assert!(enm.capabilities.iter().any(|c| c.name == "new"));
        assert!(
            !enm.capabilities.iter().any(|c| c.name == "old"),
            "the inactive 2.0.0 version must not be scanned"
        );
    }

    #[test]
    fn plugin_installed_json_selects_non_greatest_version() {
        let tmp = tempfile::tempdir().unwrap();
        // 'aaa' < 'zzz' lexically, but installed_plugins.json pins 'aaa' as active.
        let active = plugin_version_dir(tmp.path(), "mp", "p", "aaa");
        fs::create_dir_all(active.join("skills").join("chosen")).unwrap();
        fs::write(
            active.join("skills").join("chosen").join("SKILL.md"),
            b"---\nname: chosen\n---\n",
        )
        .unwrap();
        let other = plugin_version_dir(tmp.path(), "mp", "p", "zzz");
        fs::create_dir_all(other.join("skills").join("stale")).unwrap();
        fs::write(
            other.join("skills").join("stale").join("SKILL.md"),
            b"---\nname: stale\n---\n",
        )
        .unwrap();
        fs::write(
            tmp.path().join(".claude").join("plugins").join("installed_plugins.json"),
            br#"{ "version": 2, "plugins": { "p@mp": [ { "scope": "user", "version": "aaa" } ] } }"#,
        )
        .unwrap();

        let enm = enumerate_from(&[claude_agent(tmp.path())]);
        assert!(enm.capabilities.iter().any(|c| c.name == "chosen"));
        assert!(!enm.capabilities.iter().any(|c| c.name == "stale"));
    }

    #[test]
    fn in_use_lock_dir_excluded() {
        let tmp = tempfile::tempdir().unwrap();
        let skill = tmp.path().join(".claude").join("skills").join("s");
        fs::create_dir_all(skill.join(".in_use")).unwrap();
        fs::write(skill.join("SKILL.md"), b"---\nname: s\n---\n").unwrap();
        fs::write(skill.join(".in_use").join("pid-1234"), b"1234").unwrap();
        fs::write(skill.join(".in_use").join("pid-5678"), b"5678").unwrap();

        let enm = enumerate_from(&[claude_agent(tmp.path())]);
        let cap = enm.capabilities.iter().find(|c| c.name == "s").unwrap();
        assert!(!cap.entries.iter().any(|(p, _)| p.contains(".in_use")));
        assert!(enm.skips.iter().any(|s| s.reason == SkipReason::VendorDir));
    }
}
