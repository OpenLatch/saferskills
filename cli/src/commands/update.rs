//! `saferskills update [name]` / `update --all`.
//!
//! `update <name>` re-resolves the item, compares the recorded scan version to
//! the current one, and re-runs the gated install when it changed. `update --all`
//! re-verifies every installed item's score and, for any now-Red (or
//! newly-critical) item, offers to prune it (interactive) — `--prune-red` does so
//! non-interactively. Nothing is ever auto-deleted silently.

use crate::agents::writer::revert_changes;
use crate::api::dto::{Severity, Tier};
use crate::api::Api;
use crate::cli::output::OutputConfig;
use crate::cli::{Interaction, UpdateArgs};
use crate::core::config::Config;
use crate::core::error::{SsError, ERR_NEEDS_FLAG};
use crate::core::registry::{self, InstallRecord};

use super::install::{record_matches, reinstall_existing};

/// Run `update`.
pub async fn run_update(
    args: &UpdateArgs,
    inter: Interaction,
    output: &OutputConfig,
) -> Result<(), SsError> {
    let config = Config::load()?;
    let api = Api::new(config.api_base(None))?;

    if args.all {
        return update_all(&api, args, inter, output).await;
    }

    let Some(name) = args.name.as_deref() else {
        return Err(
            SsError::new(ERR_NEEDS_FLAG, "Specify an item name, or pass --all.").with_exit_code(2),
        );
    };

    let records = registry::load()?;
    let Some(record) = records.iter().find(|r| record_matches(r, name)).cloned() else {
        output.print_info(&format!("\"{name}\" is not installed."));
        return Ok(());
    };

    let detail = api.get_item(&record.slug).await?;
    let current = detail
        .latest_scan
        .as_ref()
        .and_then(|s| s.scanned_at.clone());
    if current.is_some() && current == record.version {
        output.print_step(&format!("\"{}\" is already up to date.", record.name));
        return Ok(());
    }
    reinstall_existing(&record, inter, output).await
}

#[derive(Default)]
struct Tally {
    updated: usize,
    unchanged: usize,
    red: usize,
}

async fn update_all(
    api: &Api,
    args: &UpdateArgs,
    inter: Interaction,
    output: &OutputConfig,
) -> Result<(), SsError> {
    let records = registry::load()?;
    if records.is_empty() {
        output.print_info("Nothing installed.");
        return Ok(());
    }

    let mut tally = Tally::default();
    let mut to_prune: Vec<String> = Vec::new();

    for record in &records {
        let detail = match api.get_item(&record.slug).await {
            Ok(d) => d,
            Err(e) => {
                output.print_warn(&format!("Skipping \"{}\": {}", record.name, e.message));
                continue;
            }
        };
        let tier = detail
            .item
            .latest_scan_tier
            .or_else(|| detail.latest_scan.as_ref().map(|s| s.tier))
            .unwrap_or(Tier::Unscoped);
        let new_critical = detail
            .latest_scan
            .as_ref()
            .map(|s| s.findings.iter().any(|f| f.severity == Severity::Critical))
            .unwrap_or(false);

        if tier == Tier::Red || new_critical {
            tally.red += 1;
            if should_prune(output, inter, args, &record.name, tier, new_critical)? {
                to_prune.push(record.slug.clone());
            }
            continue;
        }

        let current = detail
            .latest_scan
            .as_ref()
            .and_then(|s| s.scanned_at.clone());
        if current.is_some() && current == record.version {
            tally.unchanged += 1;
        } else {
            match reinstall_existing(record, inter, output).await {
                Ok(()) => tally.updated += 1,
                Err(e) => output.print_warn(&format!(
                    "Could not update \"{}\": {}",
                    record.name, e.message
                )),
            }
        }
    }

    // Apply prunes after the reinstalls (reload to avoid clobbering their saves).
    if !to_prune.is_empty() {
        let mut latest = registry::load()?;
        for slug in &to_prune {
            if let Some(pos) = latest.iter().position(|r: &InstallRecord| &r.slug == slug) {
                revert_changes(&latest[pos].changes)?;
                output.print_step(&format!("Pruned \"{}\" (Red).", latest[pos].name));
                latest.remove(pos);
            }
        }
        registry::save(&latest)?;
    }

    output.print_info("");
    output.print_info(&format!(
        "{} updated · {} unchanged · {} below the trust line.",
        tally.updated, tally.unchanged, tally.red
    ));
    if output.is_json() {
        output.print_json(&serde_json::json!({
            "updated": tally.updated, "unchanged": tally.unchanged, "red": tally.red,
            "pruned": to_prune.len(),
        }));
    }
    Ok(())
}

fn should_prune(
    output: &OutputConfig,
    inter: Interaction,
    args: &UpdateArgs,
    name: &str,
    tier: Tier,
    new_critical: bool,
) -> Result<bool, SsError> {
    let why = if new_critical {
        "a new critical finding"
    } else {
        "a Red score"
    };
    output.print_warn(&format!("\"{name}\" now has {why} ({}).", tier.label()));
    if args.prune_red {
        return Ok(true);
    }
    let interactive = !inter.non_interactive
        && !output.is_json()
        && !output.is_quiet()
        && std::io::IsTerminal::is_terminal(&std::io::stderr());
    if !interactive {
        // Never auto-delete non-interactively without the explicit flag.
        output.print_info("  Left in place — re-run with --prune-red to remove it.");
        return Ok(false);
    }
    Ok(inquire::Confirm::new(&format!("Uninstall \"{name}\"?"))
        .with_default(false)
        .prompt()
        .unwrap_or(false))
}
