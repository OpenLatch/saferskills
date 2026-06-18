//! The `ConfigWriter` contract + the shared install engine.
//!
//! Five install shapes — one per capability kind the platform catalogs:
//! 1. **mcp_server** → a format-preserving additive map-merge keyed by server
//!    name (`jsonc-parser` CST for JSON agents, `toml_edit` for Codex). Comments
//!    and key order survive; the prior value is captured so an uninstall restores
//!    exactly.
//! 2. **skill** → a filesystem folder copy of the capability's `SKILL.md` tree
//!    (downloaded as the SaferSkills snapshot `.zip`) into the agent's skills dir.
//! 3. **rules** → a single-file copy into the agent's rules dir with the agent's
//!    own extension (`.mdc` Cursor, `.md` Windsurf/Cline, `.instructions.md`
//!    Copilot) — an [`InstallChange::File`].
//! 4. **hook** → a per-event JSONC merge into the agent's `settings.json` `hooks`
//!    block; each event records a `hooks.<event>` [`InstallChange::ConfigKey`] so
//!    uninstall byte-restores via the shared `restore_json_key`.
//! 5. **plugin** → a native bundle install (NOT shelling out to `claude`): the
//!    `.zip` is extracted into `<plugins>/cache/<mp>/<plugin>/<ver>/` + a ledger
//!    entry merged into `installed_plugins.json` (the exact layout the local-audit
//!    enumerator reads back), recorded as a `File` + a `ConfigKey`.
//!
//! Every mutation is recorded as an [`InstallChange`] BEFORE the registry row is
//! written, so a partial failure can be reverted in LIFO order. Writes
//! are atomic (temp → fsync → rename) via [`crate::core::config::atomic_write`].
//! Uninstall/update/rollback/doctor all fall out of replaying these changes — a
//! new kind gets them for free once its install records the right `InstallChange`s.

use std::fs;
use std::io::{Cursor, Read};
use std::path::{Path, PathBuf};

use jsonc_parser::cst::{CstInputValue, CstObject, CstRootNode};
use jsonc_parser::ParseOptions;
use serde_json::Value;

use super::{AgentId, DetectedAgent, Scope};
use crate::core::config::atomic_write;
use crate::core::error::{SsError, ERR_WRITER_UNSUPPORTED, ERR_WRITE_ROLLBACK};
use crate::core::registry::InstallChange;

/// Per-writer confidence, surfaced by `doctor` for the volatile agents.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Confidence {
    High,
    Medium,
    Low,
}

impl Confidence {
    pub fn label(self) -> &'static str {
        match self {
            Confidence::High => "high",
            Confidence::Medium => "medium",
            Confidence::Low => "low",
        }
    }
}

/// Result of re-reading a config after a write (doctor / install verify).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VerifyStatus {
    /// The entry is present + well-formed.
    Ok,
    /// The config parses but the entry is gone (user removed it).
    Missing,
    /// The config no longer parses (user hand-edited it into invalid state).
    Malformed,
}

/// A resolved capability ready to install. The install flow ([`crate::commands::
/// install`]) builds this from the catalog item: an `mcp_entry` for an MCP server
/// (the `{command,args,env}` / URL object) or `skill_zip` bytes for a skill.
#[derive(Debug, Clone, Default)]
pub struct ResolvedItem {
    pub slug: String,
    /// The server/skill name — the MCP registry key + the skill folder name.
    pub name: String,
    /// `skill` | `mcp_server` | `rules` | `hook` | `plugin`
    pub kind: String,
    /// The MCP launch object to merge (mcp_server kind).
    pub mcp_entry: Option<Value>,
    /// The `.zip` bytes of the SKILL.md tree (skill kind).
    pub skill_zip: Option<Vec<u8>>,
    /// The rules-file bytes to copy into the agent's rules dir (rules kind).
    pub rules_body: Option<Vec<u8>>,
    /// The `hooks` block to merge into the agent's settings.json (hook kind) —
    /// an object of `{event: [matcher-groups]}`.
    pub hook_entry: Option<Value>,
    /// The `.zip` bytes of the plugin bundle subtree (plugin kind).
    pub plugin_zip: Option<Vec<u8>>,
    /// The capability subtree path (plugin kind) — stripped on zip extraction.
    pub component_path: Option<String>,
    /// The marketplace cache-dir name `<mp>` (plugin kind).
    pub plugin_marketplace: Option<String>,
    /// The plugin version dir name `<ver>` (plugin kind).
    pub plugin_version: Option<String>,
    /// True when the MCP launch entry was a best-effort heuristic (no server-side
    /// `install_spec`) — the install flow then nudges the user to verify it.
    pub mcp_is_heuristic: bool,
}

/// The install/uninstall/verify contract one agent's writer implements.
pub trait ConfigWriter {
    fn id(&self) -> AgentId;
    fn confidence(&self) -> Confidence;
    /// Whether this writer can install `kind` to `agent` (targeting backstop).
    fn supports_kind(&self, kind: &str, agent: &DetectedAgent) -> bool;
    /// Install `item` for `agent`, recording every change. `dry_run` plans
    /// without touching disk.
    fn install(
        &self,
        item: &ResolvedItem,
        agent: &DetectedAgent,
        dry_run: bool,
    ) -> Result<Vec<InstallChange>, SsError>;
    /// Reverse recorded changes (uninstall). Idempotent (already-gone is fine).
    fn uninstall(&self, changes: &[InstallChange]) -> Result<(), SsError>;
    /// Re-read after a write and report drift (doctor / install verify).
    fn verify(&self, item: &ResolvedItem, agent: &DetectedAgent) -> VerifyStatus;
}

// ─── serde_json::Value ↔ CST / TOML conversion ───────────────────────────────

fn json_to_cst(v: &Value) -> CstInputValue {
    match v {
        Value::Null => CstInputValue::Null,
        Value::Bool(b) => CstInputValue::Bool(*b),
        Value::Number(n) => CstInputValue::Number(n.to_string()),
        Value::String(s) => CstInputValue::String(s.clone()),
        Value::Array(a) => CstInputValue::Array(a.iter().map(json_to_cst).collect()),
        Value::Object(o) => {
            CstInputValue::Object(o.iter().map(|(k, v)| (k.clone(), json_to_cst(v))).collect())
        }
    }
}

// ─── shared file helpers ─────────────────────────────────────────────────────

fn path_str(p: &Path) -> String {
    p.to_string_lossy().into_owned()
}

fn read_or_empty(path: &Path) -> Result<String, SsError> {
    match fs::read_to_string(path) {
        Ok(s) => Ok(s),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(String::new()),
        Err(e) => Err(SsError::new(
            ERR_WRITE_ROLLBACK,
            format!("Failed to read {}: {e}", path.display()),
        )),
    }
}

fn parse_cst(source: &str, path: &Path) -> Result<CstRootNode, SsError> {
    let text = if source.trim().is_empty() {
        "{}"
    } else {
        source
    };
    CstRootNode::parse(text, &ParseOptions::default()).map_err(|e| {
        SsError::new(
            ERR_WRITE_ROLLBACK,
            format!("{} is not valid JSON: {e}", path.display()),
        )
        .with_suggestion(
            "Fix the file by hand, then re-run — SaferSkills won't overwrite invalid JSON.",
        )
    })
}

/// Navigate (creating empty objects as needed) to the container object that
/// holds MCP server entries (e.g. `mcpServers`, or `mcp` → `servers`).
fn container_or_create(root: &CstRootNode, key_path: &[&str]) -> CstObject {
    let mut cur = root.object_value_or_set();
    for seg in key_path {
        cur = cur.object_value_or_set(seg);
    }
    cur
}

fn dotted(key_path: &[&str], name: &str) -> String {
    let mut segs: Vec<&str> = key_path.to_vec();
    segs.push(name);
    segs.join(".")
}

// ─── JSON MCP merge / remove / verify ────────────────────────────────────────

/// Merge an MCP entry under `<key_path>.<name>` in a JSON config, preserving
/// comments + order. Returns the recorded change (with the prior value, if any).
pub fn merge_json_mcp(
    path: &Path,
    key_path: &[&str],
    name: &str,
    entry: &Value,
    dry_run: bool,
) -> Result<InstallChange, SsError> {
    let source = read_or_empty(path)?;
    let root = parse_cst(&source, path)?;
    let container = container_or_create(&root, key_path);

    let prior = container
        .get(name)
        .and_then(|p| p.value())
        .and_then(|n| n.to_serde_value());

    match container.get(name) {
        Some(prop) => prop.set_value(json_to_cst(entry)),
        None => {
            container.append(name, json_to_cst(entry));
        }
    }

    if !dry_run {
        atomic_write(path, root.to_string().as_bytes())?;
    }
    Ok(InstallChange::ConfigKey {
        file: path_str(path),
        key: dotted(key_path, name),
        prior,
    })
}

/// Restore (or delete) a JSON MCP key from a recorded change.
fn restore_json_key(file: &str, key: &str, prior: &Option<Value>) -> Result<(), SsError> {
    let path = PathBuf::from(file);
    let source = match fs::read_to_string(&path) {
        Ok(s) => s,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(e) => {
            return Err(SsError::new(
                ERR_WRITE_ROLLBACK,
                format!("Failed to read {}: {e}", path.display()),
            ))
        }
    };
    let root = parse_cst(&source, &path)?;
    let Some(mut container) = root.object_value() else {
        return Ok(());
    };
    let segs: Vec<&str> = key.split('.').collect();
    let Some((name, container_path)) = segs.split_last() else {
        return Ok(());
    };
    for seg in container_path {
        match container.object_value(seg) {
            Some(next) => container = next,
            None => return Ok(()), // container gone → nothing to restore
        }
    }
    match prior {
        Some(v) => match container.get(name) {
            Some(prop) => prop.set_value(json_to_cst(v)),
            None => {
                container.append(name, json_to_cst(v));
            }
        },
        None => {
            if let Some(prop) = container.get(name) {
                prop.remove();
            }
        }
    }
    atomic_write(&path, root.to_string().as_bytes())
}

pub fn verify_json_mcp(path: &Path, key_path: &[&str], name: &str) -> VerifyStatus {
    let Ok(source) = fs::read_to_string(path) else {
        return VerifyStatus::Missing;
    };
    let Ok(root) = CstRootNode::parse(
        if source.trim().is_empty() {
            "{}"
        } else {
            &source
        },
        &ParseOptions::default(),
    ) else {
        return VerifyStatus::Malformed;
    };
    let Some(mut container) = root.object_value() else {
        return VerifyStatus::Missing;
    };
    for seg in key_path {
        match container.object_value(seg) {
            Some(next) => container = next,
            None => return VerifyStatus::Missing,
        }
    }
    if container.get(name).is_some() {
        VerifyStatus::Ok
    } else {
        VerifyStatus::Missing
    }
}

/// Probe an existing OpenClaw config to pick the key shape (`mcpServers` vs the
/// nested `mcp.servers`) — its schema is ambiguous, so respect
/// whatever the file already uses; default to `mcpServers` for a fresh file.
pub fn openclaw_key(path: &Path) -> Vec<&'static str> {
    let Ok(text) = fs::read_to_string(path) else {
        return vec!["mcpServers"];
    };
    let Ok(root) = CstRootNode::parse(
        if text.trim().is_empty() { "{}" } else { &text },
        &ParseOptions::default(),
    ) else {
        return vec!["mcpServers"];
    };
    if let Some(obj) = root.object_value() {
        if obj.get("mcpServers").is_some() {
            return vec!["mcpServers"];
        }
        if let Some(mcp) = obj.object_value("mcp") {
            if mcp.get("servers").is_some() {
                return vec!["mcp", "servers"];
            }
        }
    }
    vec!["mcpServers"]
}

// ─── Codex TOML merge / remove / verify ──────────────────────────────────────

fn json_to_toml(v: &Value) -> toml_edit::Item {
    use toml_edit::{Array, Item, Value as TVal};
    match v {
        Value::Null => Item::Value(TVal::from("")),
        Value::Bool(b) => Item::Value(TVal::from(*b)),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                Item::Value(TVal::from(i))
            } else {
                Item::Value(TVal::from(n.as_f64().unwrap_or(0.0)))
            }
        }
        Value::String(s) => Item::Value(TVal::from(s.as_str())),
        Value::Array(a) => {
            let mut arr = Array::new();
            for el in a {
                if let Item::Value(val) = json_to_toml(el) {
                    arr.push(val);
                }
            }
            Item::Value(TVal::Array(arr))
        }
        Value::Object(o) => {
            let mut table = toml_edit::Table::new();
            for (k, val) in o {
                table.insert(k, json_to_toml(val));
            }
            Item::Table(table)
        }
    }
}

pub(crate) fn toml_to_json(item: &toml_edit::Item) -> Value {
    use toml_edit::Value as TVal;
    match item {
        toml_edit::Item::Value(TVal::String(s)) => Value::String(s.value().clone()),
        toml_edit::Item::Value(TVal::Integer(i)) => Value::from(*i.value()),
        toml_edit::Item::Value(TVal::Float(f)) => Value::from(*f.value()),
        toml_edit::Item::Value(TVal::Boolean(b)) => Value::Bool(*b.value()),
        toml_edit::Item::Value(TVal::Array(a)) => Value::Array(
            a.iter()
                .map(|v| toml_to_json(&toml_edit::Item::Value(v.clone())))
                .collect(),
        ),
        toml_edit::Item::Value(TVal::InlineTable(t)) => {
            let mut map = serde_json::Map::new();
            for (k, v) in t.iter() {
                map.insert(
                    k.to_string(),
                    toml_to_json(&toml_edit::Item::Value(v.clone())),
                );
            }
            Value::Object(map)
        }
        toml_edit::Item::Table(t) => {
            let mut map = serde_json::Map::new();
            for (k, v) in t.iter() {
                map.insert(k.to_string(), toml_to_json(v));
            }
            Value::Object(map)
        }
        _ => Value::Null,
    }
}

/// Merge an MCP entry under `[mcp_servers.<name>]` in a Codex `config.toml`,
/// preserving comments + formatting via `toml_edit`.
pub fn merge_toml_mcp(
    path: &Path,
    name: &str,
    entry: &Value,
    dry_run: bool,
) -> Result<InstallChange, SsError> {
    let source = read_or_empty(path)?;
    let mut doc = source.parse::<toml_edit::DocumentMut>().map_err(|e| {
        SsError::new(
            ERR_WRITE_ROLLBACK,
            format!("{} is not valid TOML: {e}", path.display()),
        )
        .with_suggestion("Fix the file by hand, then re-run.")
    })?;

    let prior = doc
        .get("mcp_servers")
        .and_then(|s| s.get(name))
        .map(toml_to_json);

    if doc.get("mcp_servers").is_none() {
        doc["mcp_servers"] = toml_edit::Item::Table(toml_edit::Table::new());
    }
    doc["mcp_servers"][name] = json_to_toml(entry);

    if !dry_run {
        atomic_write(path, doc.to_string().as_bytes())?;
    }
    Ok(InstallChange::ConfigKey {
        file: path_str(path),
        key: format!("mcp_servers.{name}"),
        prior,
    })
}

fn restore_toml_key(file: &str, key: &str, prior: &Option<Value>) -> Result<(), SsError> {
    let path = PathBuf::from(file);
    let Ok(source) = fs::read_to_string(&path) else {
        return Ok(());
    };
    let mut doc = match source.parse::<toml_edit::DocumentMut>() {
        Ok(d) => d,
        Err(_) => return Ok(()),
    };
    let name = key.strip_prefix("mcp_servers.").unwrap_or(key);
    match prior {
        Some(v) => {
            if doc.get("mcp_servers").is_none() {
                doc["mcp_servers"] = toml_edit::Item::Table(toml_edit::Table::new());
            }
            doc["mcp_servers"][name] = json_to_toml(v);
        }
        None => {
            if let Some(servers) = doc.get_mut("mcp_servers").and_then(|s| s.as_table_mut()) {
                servers.remove(name);
            }
        }
    }
    atomic_write(&path, doc.to_string().as_bytes())
}

pub fn verify_toml_mcp(path: &Path, name: &str) -> VerifyStatus {
    let Ok(source) = fs::read_to_string(path) else {
        return VerifyStatus::Missing;
    };
    let Ok(doc) = source.parse::<toml_edit::DocumentMut>() else {
        return VerifyStatus::Malformed;
    };
    if doc.get("mcp_servers").and_then(|s| s.get(name)).is_some() {
        VerifyStatus::Ok
    } else {
        VerifyStatus::Missing
    }
}

// ─── skill folder copy ───────────────────────────────────────────────────────

/// Path components are rejected if any is `..` or absolute (zip-slip guard).
fn safe_join(base: &Path, rel: &str) -> Option<PathBuf> {
    let mut out = base.to_path_buf();
    for comp in Path::new(rel).components() {
        match comp {
            std::path::Component::Normal(c) => out.push(c),
            std::path::Component::CurDir => {}
            _ => return None, // ParentDir / RootDir / Prefix → reject
        }
    }
    Some(out)
}

/// Strip a `component_path` prefix from a zip entry's rel-path so a per-capability
/// subtree extracts at the destination root. A repo-wide entry (LICENSE/README at
/// the repo root, no prefix) is kept verbatim. Returns None for the prefix dir
/// entry itself (nothing to write).
fn strip_component_prefix(rel: &str, prefix: &str) -> Option<String> {
    let rel = rel.replace('\\', "/");
    if prefix.is_empty() {
        return Some(rel);
    }
    let prefix = prefix.trim_end_matches('/');
    match rel.strip_prefix(prefix).and_then(|r| r.strip_prefix('/')) {
        Some(s) if !s.is_empty() => Some(s.to_string()),
        Some(_) => None,   // the prefix dir entry itself
        None => Some(rel), // a sibling repo-wide file → keep at root
    }
}

/// Extract a `.zip` into `dest`, stripping `strip_prefix` from each entry (zip-slip
/// guarded). Shared by skill + plugin installs.
fn unzip_into(dest: &Path, zip_bytes: &[u8], strip_prefix: &str) -> Result<(), SsError> {
    let mut archive = zip::ZipArchive::new(Cursor::new(zip_bytes))
        .map_err(|e| SsError::new(ERR_WRITE_ROLLBACK, format!("Invalid archive: {e}")))?;
    fs::create_dir_all(dest).map_err(|e| {
        SsError::new(
            ERR_WRITE_ROLLBACK,
            format!("Failed to create {}: {e}", dest.display()),
        )
    })?;
    for i in 0..archive.len() {
        let mut entry = archive
            .by_index(i)
            .map_err(|e| SsError::new(ERR_WRITE_ROLLBACK, format!("Corrupt archive: {e}")))?;
        let raw = entry.name().to_string();
        let Some(rel) = strip_component_prefix(&raw, strip_prefix) else {
            continue;
        };
        let Some(target) = safe_join(dest, &rel) else {
            return Err(SsError::new(
                ERR_WRITE_ROLLBACK,
                format!("Refusing unsafe path in archive: {raw}"),
            ));
        };
        if entry.is_dir() {
            fs::create_dir_all(&target).ok();
            continue;
        }
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).ok();
        }
        let mut buf = Vec::new();
        entry.read_to_end(&mut buf).map_err(|e| {
            SsError::new(
                ERR_WRITE_ROLLBACK,
                format!("Failed to read archive entry: {e}"),
            )
        })?;
        atomic_write(&target, &buf)?;
    }
    Ok(())
}

/// Extract the skill `.zip` into `<skill_dir>/<name>/`, returning the folder root
/// as the recorded change (uninstall removes the folder).
pub fn install_skill(
    skill_dir: &Path,
    name: &str,
    zip_bytes: &[u8],
    dry_run: bool,
) -> Result<InstallChange, SsError> {
    let dest = skill_dir.join(name);
    if dry_run {
        return Ok(InstallChange::File {
            path: path_str(&dest),
        });
    }
    unzip_into(&dest, zip_bytes, "")?;
    Ok(InstallChange::File {
        path: path_str(&dest),
    })
}

// ─── rules file copy ─────────────────────────────────────────────────────────

/// Copy a rules body to `<rules_dir>/<file_name>`, returning the file as the
/// recorded change (uninstall removes it). Verify = the file exists.
pub fn install_rules_file(
    rules_dir: &Path,
    file_name: &str,
    body: &[u8],
    dry_run: bool,
) -> Result<InstallChange, SsError> {
    let dest = rules_dir.join(file_name);
    if !dry_run {
        if let Some(parent) = dest.parent() {
            fs::create_dir_all(parent).map_err(|e| {
                SsError::new(
                    ERR_WRITE_ROLLBACK,
                    format!("Failed to create {}: {e}", parent.display()),
                )
            })?;
        }
        atomic_write(&dest, body)?;
    }
    Ok(InstallChange::File {
        path: path_str(&dest),
    })
}

// ─── hook settings.json merge ────────────────────────────────────────────────

/// Merge a `hooks` block (`{event: [matcher-groups]}`) into `settings_path` under
/// the top-level `hooks` key, preserving comments + order. Records ONE change per
/// event — `ConfigKey { key: "hooks.<event>", prior: <prior event value> }` — so
/// uninstall reuses the dotted-key `restore_json_key`: a NEW event is removed
/// (prior `None` → byte-for-byte, untouched siblings preserved), an existing event
/// is restored to its prior array. New events append; an existing event has the
/// source matcher-groups appended to its array.
pub fn merge_json_hook(
    settings_path: &Path,
    hook_block: &Value,
    dry_run: bool,
) -> Result<Vec<InstallChange>, SsError> {
    let Value::Object(events) = hook_block else {
        return Err(SsError::new(
            ERR_WRITE_ROLLBACK,
            "Hook spec is not an object of {event: [groups]}.",
        ));
    };
    let source = read_or_empty(settings_path)?;
    let root = parse_cst(&source, settings_path)?;
    let root_obj = root.object_value_or_set();
    let hooks = root_obj.object_value_or_set("hooks");

    let mut changes = Vec::new();
    for (event, groups) in events {
        if !matches!(groups, Value::Array(_)) {
            continue;
        }
        // Per-event prior captured BEFORE we touch it (None when the event is new).
        let prior = hooks
            .get(event)
            .and_then(|p| p.value())
            .and_then(|n| n.to_serde_value());
        match hooks.get(event) {
            Some(prop) => {
                // Append the source matcher-groups to the existing event array.
                let mut merged = match prop.value().and_then(|v| v.to_serde_value()) {
                    Some(Value::Array(a)) => a,
                    _ => Vec::new(),
                };
                if let Value::Array(new_groups) = groups {
                    merged.extend(new_groups.iter().cloned());
                }
                prop.set_value(json_to_cst(&Value::Array(merged)));
            }
            None => {
                hooks.append(event, json_to_cst(groups));
            }
        }
        changes.push(InstallChange::ConfigKey {
            file: path_str(settings_path),
            key: format!("hooks.{event}"),
            prior,
        });
    }

    if !dry_run {
        atomic_write(settings_path, root.to_string().as_bytes())?;
    }
    Ok(changes)
}

/// Verify a hook install — every `event` is present under `hooks` in the settings.
pub fn verify_hook(settings_path: &Path, events: &[String]) -> VerifyStatus {
    let Ok(source) = fs::read_to_string(settings_path) else {
        return VerifyStatus::Missing;
    };
    let Ok(root) = CstRootNode::parse(
        if source.trim().is_empty() {
            "{}"
        } else {
            &source
        },
        &ParseOptions::default(),
    ) else {
        return VerifyStatus::Malformed;
    };
    let Some(obj) = root.object_value() else {
        return VerifyStatus::Missing;
    };
    let Some(hooks) = obj.object_value("hooks") else {
        return VerifyStatus::Missing;
    };
    if events.iter().all(|e| hooks.get(e).is_some()) {
        VerifyStatus::Ok
    } else {
        VerifyStatus::Missing
    }
}

// ─── plugin bundle install ───────────────────────────────────────────────────

/// Install a plugin bundle the way Claude Code's own cache reads it (NOT shelling
/// out to `claude`, which would forfeit the reversible-install guarantee):
/// extract the `.zip` (prefix-stripped to `component_path`) into
/// `<plugins_root>/cache/<mp>/<plugin>/<version>/`, then merge a ledger entry into
/// `<plugins_root>/installed_plugins.json`. Records the version dir as a `File`
/// change + the ledger as a `ConfigKey` (restoring the whole prior `plugins` map),
/// so a LIFO uninstall removes both.
#[allow(clippy::too_many_arguments)]
pub fn install_plugin(
    plugins_root: &Path,
    mp: &str,
    plugin: &str,
    version: &str,
    component_path: &str,
    zip_bytes: &[u8],
    dry_run: bool,
) -> Result<Vec<InstallChange>, SsError> {
    let version_dir = plugins_root
        .join("cache")
        .join(mp)
        .join(plugin)
        .join(version);
    let ledger_path = plugins_root.join("installed_plugins.json");

    // Ledger merge (records the prior whole `plugins` map for an exact restore).
    let source = read_or_empty(&ledger_path)?;
    let root = parse_cst(&source, &ledger_path)?;
    let root_obj = root.object_value_or_set();
    let prior = root_obj
        .get("plugins")
        .and_then(|p| p.value())
        .and_then(|n| n.to_serde_value());
    let plugins = root_obj.object_value_or_set("plugins");

    let ledger_key = format!("{plugin}@{mp}");
    let install = serde_json::json!({ "scope": "user", "version": version });
    match plugins.get(&ledger_key) {
        Some(prop) => {
            // Existing entry → append this install to its `installs[]` (serde-land
            // merge, then set the merged object back).
            let mut entry = match prop.value().and_then(|v| v.to_serde_value()) {
                Some(Value::Object(m)) => m,
                _ => serde_json::Map::new(),
            };
            let mut installs = match entry.get("installs") {
                Some(Value::Array(a)) => a.clone(),
                _ => Vec::new(),
            };
            installs.push(install);
            entry.insert("installs".to_string(), Value::Array(installs));
            prop.set_value(json_to_cst(&Value::Object(entry)));
        }
        None => {
            plugins.append(
                &ledger_key,
                json_to_cst(&serde_json::json!({ "installs": [install] })),
            );
        }
    }

    if !dry_run {
        unzip_into(&version_dir, zip_bytes, component_path)?;
        atomic_write(&ledger_path, root.to_string().as_bytes())?;
    }
    // File first, ConfigKey second → LIFO revert restores the ledger then the dir.
    Ok(vec![
        InstallChange::File {
            path: path_str(&version_dir),
        },
        InstallChange::ConfigKey {
            file: path_str(&ledger_path),
            key: "plugins".to_string(),
            prior,
        },
    ])
}

/// Verify a plugin install — the version dir exists AND the ledger lists it.
pub fn verify_plugin(plugins_root: &Path, mp: &str, plugin: &str, version: &str) -> VerifyStatus {
    let version_dir = plugins_root
        .join("cache")
        .join(mp)
        .join(plugin)
        .join(version);
    if !version_dir.is_dir() {
        return VerifyStatus::Missing;
    }
    let ledger_path = plugins_root.join("installed_plugins.json");
    let Ok(source) = fs::read_to_string(&ledger_path) else {
        return VerifyStatus::Missing;
    };
    let Ok(root) = CstRootNode::parse(
        if source.trim().is_empty() {
            "{}"
        } else {
            &source
        },
        &ParseOptions::default(),
    ) else {
        return VerifyStatus::Malformed;
    };
    let present = root
        .object_value()
        .and_then(|o| o.object_value("plugins"))
        .and_then(|p| p.get(&format!("{plugin}@{mp}")))
        .is_some();
    if present {
        VerifyStatus::Ok
    } else {
        VerifyStatus::Missing
    }
}

fn remove_path(path: &str) -> Result<(), SsError> {
    let p = PathBuf::from(path);
    let res = if p.is_dir() {
        fs::remove_dir_all(&p)
    } else if p.exists() {
        fs::remove_file(&p)
    } else {
        return Ok(());
    };
    res.map_err(|e| SsError::new(ERR_WRITE_ROLLBACK, format!("Failed to remove {path}: {e}")))
}

// ─── reusable uninstall over recorded changes ────────────────────────────────

/// Reverse a recorded change list in LIFO order. The file extension
/// selects the JSON vs TOML restore path. Shared by every writer's `uninstall`.
pub fn revert_changes(changes: &[InstallChange]) -> Result<(), SsError> {
    for change in changes.iter().rev() {
        match change {
            InstallChange::File { path } => remove_path(path)?,
            InstallChange::ConfigKey { file, key, prior } => {
                if file.ends_with(".toml") {
                    restore_toml_key(file, key, prior)?;
                } else {
                    restore_json_key(file, key, prior)?;
                }
            }
        }
    }
    Ok(())
}

/// The shared kind-support backstop used by every writer's `supports_kind`. A
/// writer can install `kind` for `agent` iff the agent exposes the surface that
/// kind needs (the backend `agent_compatibility` is the outer filter, so a writer
/// never sees a kind its agent can't take — this is the on-disk-surface check).
pub fn kind_supported(kind: &str, agent: &DetectedAgent) -> bool {
    match kind {
        "mcp_server" => true,
        "skill" => agent.skill_dir.is_some(),
        "rules" => agent.rules_dir.is_some(),
        "hook" => agent.hooks_path.is_some(),
        "plugin" => agent.plugin_dir.is_some(),
        _ => false,
    }
}

/// Guard: reject a project-scope install for an agent whose config is global-only.
pub fn reject_project_if_unsupported(
    supports_project: bool,
    agent: &DetectedAgent,
) -> Result<(), SsError> {
    if !supports_project && agent.scope == Scope::Project {
        return Err(SsError::new(
            ERR_WRITER_UNSUPPORTED,
            format!(
                "{} has no project-scoped config — it is global-only.",
                agent.id.display_name()
            ),
        )
        .with_suggestion("Re-run without --project to install globally."));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entry() -> Value {
        serde_json::json!({"command": "npx", "args": ["-y", "pkg"], "env": {}})
    }

    #[test]
    fn json_merge_preserves_comments_and_records_prior() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("mcp.json");
        fs::write(&path, "{\n  // keep me\n  \"mcpServers\": {}\n}\n").unwrap();

        let change = merge_json_mcp(&path, &["mcpServers"], "github", &entry(), false).unwrap();
        let after = fs::read_to_string(&path).unwrap();
        assert!(after.contains("// keep me"), "comment preserved: {after}");
        assert!(after.contains("\"github\""));
        match change {
            InstallChange::ConfigKey { key, prior, .. } => {
                assert_eq!(key, "mcpServers.github");
                assert!(prior.is_none());
            }
            _ => panic!("expected ConfigKey"),
        }
        assert_eq!(
            verify_json_mcp(&path, &["mcpServers"], "github"),
            VerifyStatus::Ok
        );
    }

    #[test]
    fn json_uninstall_restores_byte_for_byte() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("mcp.json");
        let original =
            "{\n  // header\n  \"mcpServers\": {\n    \"other\": { \"command\": \"x\" }\n  }\n}\n";
        fs::write(&path, original).unwrap();

        let change = merge_json_mcp(&path, &["mcpServers"], "github", &entry(), false).unwrap();
        assert!(fs::read_to_string(&path).unwrap().contains("github"));
        revert_changes(&[change]).unwrap();
        assert_eq!(fs::read_to_string(&path).unwrap(), original);
    }

    #[test]
    fn json_merge_into_missing_file_creates_it() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("nested").join("mcp.json");
        let change = merge_json_mcp(&path, &["mcpServers"], "g", &entry(), false).unwrap();
        assert_eq!(
            verify_json_mcp(&path, &["mcpServers"], "g"),
            VerifyStatus::Ok
        );
        revert_changes(&[change]).unwrap();
        // prior was None → key removed; the (now empty) container remains valid JSON.
        assert_eq!(
            verify_json_mcp(&path, &["mcpServers"], "g"),
            VerifyStatus::Missing
        );
    }

    #[test]
    fn nested_key_path_for_openclaw_style() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("openclaw.json");
        fs::write(&path, "{\n  \"mcp\": { \"servers\": {} }\n}\n").unwrap();
        assert_eq!(openclaw_key(&path), vec!["mcp", "servers"]);
        let change = merge_json_mcp(&path, &["mcp", "servers"], "g", &entry(), false).unwrap();
        assert_eq!(
            verify_json_mcp(&path, &["mcp", "servers"], "g"),
            VerifyStatus::Ok
        );
        revert_changes(&[change]).unwrap();
    }

    #[test]
    fn openclaw_key_defaults_to_mcpservers_for_fresh_file() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("nope.json");
        assert_eq!(openclaw_key(&path), vec!["mcpServers"]);
    }

    #[test]
    fn toml_merge_and_uninstall() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.toml");
        fs::write(&path, "# codex config\nmodel = \"o3\"\n").unwrap();

        let change = merge_toml_mcp(&path, "github", &entry(), false).unwrap();
        let after = fs::read_to_string(&path).unwrap();
        assert!(after.contains("# codex config"), "comment preserved");
        assert!(after.contains("[mcp_servers.github]"));
        assert_eq!(verify_toml_mcp(&path, "github"), VerifyStatus::Ok);

        revert_changes(&[change]).unwrap();
        assert_eq!(verify_toml_mcp(&path, "github"), VerifyStatus::Missing);
        assert!(fs::read_to_string(&path)
            .unwrap()
            .contains("model = \"o3\""));
    }

    #[test]
    fn skill_install_and_uninstall() {
        let dir = tempfile::tempdir().unwrap();
        let skills = dir.path().join("skills");
        // Build a tiny in-memory zip with SKILL.md.
        let mut buf = Vec::new();
        {
            let mut w = zip::ZipWriter::new(Cursor::new(&mut buf));
            let opts: zip::write::FileOptions<'_, ()> = zip::write::FileOptions::default();
            use std::io::Write as _;
            w.start_file("SKILL.md", opts).unwrap();
            w.write_all(b"---\nname: pdf\n---\n").unwrap();
            w.finish().unwrap();
        }
        let change = install_skill(&skills, "pdf", &buf, false).unwrap();
        assert!(skills.join("pdf").join("SKILL.md").exists());
        revert_changes(&[change]).unwrap();
        assert!(!skills.join("pdf").exists());
    }

    #[test]
    fn dry_run_writes_nothing() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("mcp.json");
        let change = merge_json_mcp(&path, &["mcpServers"], "g", &entry(), true).unwrap();
        assert!(!path.exists(), "dry-run must not write");
        assert!(matches!(change, InstallChange::ConfigKey { .. }));
    }

    #[test]
    fn safe_join_rejects_traversal() {
        let base = Path::new("/tmp/x");
        assert!(safe_join(base, "a/b.txt").is_some());
        assert!(safe_join(base, "../escape").is_none());
    }
}
