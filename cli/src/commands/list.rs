//! `saferskills list` (D-05-18, CLI-7).
//!
//! Reads the install registry and re-fetches each item's current score so a
//! drift since install (`⚠ score dropped 87→61`) surfaces inline. `--json` emits
//! the registry enriched with the current score/tier.

use crate::api::dto::Tier;
use crate::api::Api;
use crate::cli::color;
use crate::cli::output::OutputConfig;
use crate::cli::ListArgs;
use crate::core::config::Config;
use crate::core::error::SsError;
use crate::core::registry;

/// Run `list`.
pub async fn run_list(_args: &ListArgs, output: &OutputConfig) -> Result<(), SsError> {
    let config = Config::load()?;
    let api = Api::new(config.api_base(None))?;
    let records = registry::load()?;

    if records.is_empty() {
        if output.is_json() {
            output.print_json(&serde_json::json!({ "data": [] }));
        } else {
            output.print_info("Nothing installed yet. Try: saferskills install <name>");
        }
        return Ok(());
    }

    let mut rows: Vec<serde_json::Value> = Vec::new();
    for r in &records {
        // Best-effort current score (offline → just show the install-time score).
        let (current, tier) = match api.get_item(&r.slug).await {
            Ok(d) => (
                d.item
                    .latest_scan_score
                    .or_else(|| d.latest_scan.as_ref().map(|s| s.aggregate_score)),
                d.item
                    .latest_scan_tier
                    .or_else(|| d.latest_scan.as_ref().map(|s| s.tier))
                    .unwrap_or(Tier::Unscoped),
            ),
            Err(_) => (r.seen_score, Tier::Unknown),
        };

        if !output.is_json() {
            let score_str = current
                .map(|v| format!("{v}/100"))
                .unwrap_or_else(|| "—".into());
            let agents = r.agents.join(", ");
            output.print_info(&format!(
                "{}  {}  [{}]  {}  {score_str}",
                color::bold(&r.name, output.color),
                color::dim(&r.kind, output.color),
                agents,
                color::tier_dot(tier, output.color),
            ));
            if let (Some(seen), Some(now)) = (r.seen_score, current) {
                if now < seen {
                    output.print_info(&color::dim(
                        &format!(
                            "    {} score dropped {seen}→{now} since install",
                            color::warn_glyph(output.color)
                        ),
                        output.color,
                    ));
                }
            }
        }

        rows.push(serde_json::json!({
            "slug": r.slug,
            "name": r.name,
            "kind": r.kind,
            "agents": r.agents,
            "installed_version": r.version,
            "seen_score": r.seen_score,
            "current_score": current,
            "tier": tier,
        }));
    }

    if output.is_json() {
        output.print_json(&serde_json::json!({ "data": rows }));
    }
    Ok(())
}
