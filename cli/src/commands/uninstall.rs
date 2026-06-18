//! `saferskills uninstall <name> [--from <agent>]` (D-05-18).
//!
//! Reverses exactly the recorded changes (LIFO via the writer engine) and drops
//! the registry row. `--from` scopes the removal to a single agent (reverting
//! only the changes located under that agent's config/skill paths + pruning it
//! from the record). Idempotent: an unknown name exits 0 with a note.

use std::io::IsTerminal;
use std::path::PathBuf;

use crate::agents::writer::revert_changes;
use crate::agents::{detect, AgentId, Scope};
use crate::cli::output::OutputConfig;
use crate::cli::{Interaction, UninstallArgs};
use crate::core::error::{SsError, ERR_GATE_CANCELLED, ERR_UNKNOWN_AGENT};
use crate::core::registry::{self, InstallChange};

use super::install::record_matches;

/// Run `uninstall`.
pub async fn run_uninstall(
    args: &UninstallArgs,
    inter: Interaction,
    output: &OutputConfig,
) -> Result<(), SsError> {
    let mut records = registry::load()?;
    let Some(idx) = records.iter().position(|r| record_matches(r, &args.name)) else {
        output.print_info(&format!(
            "\"{}\" is not installed — nothing to do.",
            args.name
        ));
        return Ok(());
    };

    // Resolve an optional --from agent filter.
    let from = match &args.from {
        Some(raw) => {
            let (id, warning) = AgentId::parse_cli(raw).map_err(|_| {
                SsError::new(ERR_UNKNOWN_AGENT, format!("Unknown agent: \"{raw}\""))
                    .with_exit_code(2)
            })?;
            if let Some(w) = warning {
                output.print_warn(&w);
            }
            Some(id)
        }
        None => None,
    };

    if !confirm_removal(output, inter, &records[idx].name, from)? {
        return Err(SsError::new(ERR_GATE_CANCELLED, "Uninstall cancelled."));
    }

    let record = &mut records[idx];
    match from {
        None => {
            revert_changes(&record.changes)?;
            output.print_step(&format!("Removed \"{}\" from all agents.", record.name));
            records.remove(idx);
        }
        Some(id) => {
            let dirs = agent_dirs(id);
            let (mine, rest): (Vec<InstallChange>, Vec<InstallChange>) = record
                .changes
                .clone()
                .into_iter()
                .partition(|c| change_under(c, &dirs));
            if mine.is_empty() {
                output.print_info(&format!(
                    "Nothing recorded for {} on \"{}\".",
                    id.display_name(),
                    record.name
                ));
                return Ok(());
            }
            revert_changes(&mine)?;
            record.changes = rest;
            record.agents.retain(|a| a != id.as_str());
            output.print_step(&format!(
                "Removed \"{}\" from {}.",
                record.name,
                id.display_name()
            ));
            if record.agents.is_empty() {
                records.remove(idx);
            }
        }
    }

    registry::save(&records)?;
    Ok(())
}

fn confirm_removal(
    output: &OutputConfig,
    inter: Interaction,
    name: &str,
    from: Option<AgentId>,
) -> Result<bool, SsError> {
    if inter.yes || inter.force {
        return Ok(true);
    }
    let interactive = !inter.non_interactive
        && !output.is_json()
        && !output.is_quiet()
        && std::io::stderr().is_terminal();
    if !interactive {
        // Non-interactive uninstall proceeds (it is reversible + intended); the
        // user explicitly named the item.
        return Ok(true);
    }
    let scope = from
        .map(|id| format!(" from {}", id.display_name()))
        .unwrap_or_default();
    Ok(
        inquire::Confirm::new(&format!("Uninstall \"{name}\"{scope}?"))
            .with_default(true)
            .prompt()
            .unwrap_or(false),
    )
}

/// Candidate paths a change must fall under to belong to `id` (both scopes,
/// de-detected). Directory entries (config/skill/rules/hook/plugin roots) match
/// any change beneath them; the shared `AGENTS.md`/`GEMINI.md` is pushed as an
/// EXACT file path (not its directory) — every project change lives under the
/// project root, so a raw-dir entry would let `--from <any-agent>` strip the
/// codex/copilot skill block it doesn't own.
fn agent_dirs(id: AgentId) -> Vec<PathBuf> {
    let mut dirs = Vec::new();
    for scope in [Scope::Global, Scope::Project] {
        if let Some(a) = detect::detect(id, scope) {
            dirs.push(a.mcp_config_path.clone());
            // Only a marker agent (codex/copilot/gemini) owns an AGENTS.md/GEMINI.md
            // skill block — push the EXACT host file the renderer wrote to.
            //
            // Known limitation (left as-is, by design): codex + copilot share the
            // SAME `./AGENTS.md`, so `--from codex` while copilot is still installed
            // strips the shared block. `revert_marker_block` no-ops gracefully if the
            // block is already gone, so this is safe — just broader than ideal. We do
            // NOT build cross-agent block-ownership tracking.
            if crate::agents::writers::is_agents_md_agent(id) {
                if let Ok(host) = crate::agents::writers::agents_md_path(id, &a) {
                    dirs.push(host);
                }
            }
            for extra in [a.skill_dir, a.rules_dir, a.hooks_path, a.plugin_dir]
                .into_iter()
                .flatten()
            {
                dirs.push(extra);
            }
        }
    }
    dirs
}

fn change_under(change: &InstallChange, dirs: &[PathBuf]) -> bool {
    let target = match change {
        InstallChange::File { path } => path,
        InstallChange::ConfigKey { file, .. } => file,
        InstallChange::MarkerBlock { file, .. } => file,
    };
    // Component-aware prefix match (NOT string `starts_with`): an exact-file entry
    // matches the identical target (a path starts-with itself), a directory entry
    // matches any change beneath it, and `/foo/barbaz` no longer matches `/foo/bar`.
    let target_path = std::path::Path::new(target);
    dirs.iter().any(|d| target_path.starts_with(d))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn marker_change(file: &str) -> InstallChange {
        InstallChange::MarkerBlock {
            file: file.into(),
            prior: None,
        }
    }

    /// FIX 2: `--from <non-marker agent>` must NOT match the codex/copilot AGENTS.md
    /// marker block. We drive `change_under` with the dir lists the NEW `agent_dirs`
    /// produces (a non-marker agent: only its config/rules dirs; a marker agent: its
    /// config dir + the EXACT AGENTS.md path) — built explicitly here so the test is
    /// hermetic (live `agent_dirs` depends on which agents are installed on the box).
    #[test]
    fn marker_block_scoped_to_its_owning_agent() {
        let agents_md = marker_change("/proj/AGENTS.md");

        // Cursor's dirs (post-fix): config + rules dir only — NO raw cwd, so the
        // shared AGENTS.md is NOT under any of them.
        let cursor_dirs = vec![
            PathBuf::from("/proj/.cursor/mcp.json"),
            PathBuf::from("/proj/.cursor/rules"),
        ];
        assert!(
            !change_under(&agents_md, &cursor_dirs),
            "cursor does not own AGENTS.md"
        );

        // Codex's dirs (post-fix): config + the EXACT AGENTS.md path.
        let codex_dirs = vec![
            PathBuf::from("/proj/.codex/config.toml"),
            PathBuf::from("/proj/AGENTS.md"),
        ];
        assert!(
            change_under(&agents_md, &codex_dirs),
            "codex owns AGENTS.md"
        );
    }

    /// FIX 2: component-aware match — `/foo/barbaz` is NOT under the `/foo/bar` dir.
    #[test]
    fn change_under_is_component_aware_not_string_prefix() {
        let dirs = vec![PathBuf::from("/foo/bar")];
        // Sibling whose string prefix matches but whose path components do not.
        assert!(!change_under(
            &InstallChange::File {
                path: "/foo/barbaz/x".into()
            },
            &dirs
        ));
        // A real child still matches.
        assert!(change_under(
            &InstallChange::File {
                path: "/foo/bar/child.md".into()
            },
            &dirs
        ));
        // An exact-file dir entry matches the identical target.
        let exact = vec![PathBuf::from("/foo/AGENTS.md")];
        assert!(change_under(&marker_change("/foo/AGENTS.md"), &exact));
        // …but not a different file in the same directory.
        assert!(!change_under(&marker_change("/foo/GEMINI.md"), &exact));
    }
}
