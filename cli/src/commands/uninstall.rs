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

/// Candidate path prefixes a change must fall under to belong to `id` (both
/// scopes, de-detected).
fn agent_dirs(id: AgentId) -> Vec<PathBuf> {
    let mut dirs = Vec::new();
    for scope in [Scope::Global, Scope::Project] {
        if let Some(a) = detect::detect(id, scope) {
            dirs.push(a.mcp_config_path.clone());
            if let Some(sd) = a.skill_dir {
                dirs.push(sd);
            }
        }
    }
    dirs
}

fn change_under(change: &InstallChange, dirs: &[PathBuf]) -> bool {
    let target = match change {
        InstallChange::File { path } => path,
        InstallChange::ConfigKey { file, .. } => file,
    };
    dirs.iter().any(|d| {
        let d = d.to_string_lossy();
        target == &*d || target.starts_with(&*d)
    })
}
