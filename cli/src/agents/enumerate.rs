//! Local-install enumeration — audit every capability *already installed* across
//! detected agents (D-05-27).
//!
//! `scan --local` answers "audit everything I have installed", which is a
//! different question from the CLI's own install ledger (`core::registry`, which
//! only knows what *saferskills* installed). This module reads each detected
//! agent's *own* config dirs/files — `agent.skill_dir`, `agent.mcp_config_path`,
//! and the hook/rules roots derived from them — and emits one [`LocalCapability`]
//! per skill / MCP server / hook / rules file found, regardless of how it was
//! installed. The result is bundled into one structured `.zip` (paths matching
//! the backend `discovery.py` anchor layout) and uploaded once.
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
/// backend kind. `Plugin` is carried for forward-compat (not discovered in v1).
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
    pub const MAX_ENTRIES: usize = 900;

    /// Directories never bundled (VCS / build / dependency vendor trees).
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
    if !skill_dir.is_dir() {
        return; // no skills installed for this agent
    }
    let mut children: Vec<PathBuf> = match std::fs::read_dir(skill_dir) {
        Ok(rd) => rd.filter_map(|e| e.ok().map(|e| e.path())).collect(),
        Err(_) => {
            skips.push(SkipNote::at(
                agent.id,
                skill_dir.to_string_lossy(),
                SkipReason::Unreadable,
            ));
            return;
        }
    };
    children.sort();
    let agent_seg = agent.id.as_str();
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
        let mount = format!("{agent_seg}/skills/{name}");
        let anchor = format!("{mount}/{anchor_name}");
        if let Some(cap) = collect_dir_capability(
            agent.id,
            CapKind::Skill,
            &name,
            &child,
            &mount,
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
    if agent.id == AgentId::Codex {
        discover_mcp_toml(agent, out, skips);
        return;
    }
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
    let value = match parse_jsonc(&text) {
        Some(v) => v,
        None => {
            skips.push(SkipNote::at(
                agent.id,
                path.to_string_lossy(),
                SkipReason::MalformedConfig,
            ));
            return;
        }
    };
    let key = mcp_key_path(agent);
    let key_refs: Vec<&str> = key.iter().map(String::as_str).collect();
    let Some(map) = navigate_object(&value, &key_refs) else {
        return; // no server map under the expected key — nothing installed
    };
    for (name, entry) in map {
        out.push(make_mcp_cap(agent.id, path, name, entry));
    }
}

fn discover_mcp_toml(
    agent: &DetectedAgent,
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
        out.push(make_mcp_cap(agent.id, path, name, &entry));
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
fn make_mcp_cap(agent: AgentId, origin: &Path, name: &str, entry: &Value) -> LocalCapability {
    let seg = sanitize_segment(name);
    let mount = format!("{}/mcp/{}", agent.as_str(), seg);
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
    if hooks_dir.is_dir() {
        let mut files: Vec<PathBuf> = match std::fs::read_dir(&hooks_dir) {
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
                    let synth = format!("{agent_seg}/hooks/{fname}");
                    out.push(single_file_cap(
                        agent.id,
                        CapKind::Hook,
                        stem,
                        &path,
                        synth,
                        bytes,
                    ));
                }
                Err(_) => skips.push(SkipNote::at(
                    agent.id,
                    path.to_string_lossy(),
                    SkipReason::Unreadable,
                )),
            }
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
            let is_anchor = rel == anchor_rel;
            if !is_anchor {
                if let Some(reason) = excluded_ext_reason(&rel) {
                    skips.push(SkipNote::at(agent, synth, reason));
                    continue;
                }
                if let Ok(meta) = std::fs::metadata(&path) {
                    if meta.len() as usize > budget::MAX_FILE_BYTES {
                        skips.push(SkipNote::at(agent, synth, SkipReason::TooLargeFile));
                        continue;
                    }
                }
            }
            let bytes = match std::fs::read(&path) {
                Ok(b) => b,
                Err(_) => {
                    skips.push(SkipNote::at(agent, synth, SkipReason::Unreadable));
                    continue;
                }
            };
            if !is_anchor && looks_binary(&bytes) {
                skips.push(SkipNote::at(agent, synth, SkipReason::Binary));
                continue;
            }
            entries.push((synth, bytes));
        }
    }
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
    others.sort_by(|a, b| a.1.len().cmp(&b.1.len()));
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
            scope: Scope::Global,
        }
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
}
