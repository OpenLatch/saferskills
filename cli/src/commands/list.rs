//! `saferskills list` — full local inventory + scores + scan invitation.
//!
//! `list` shows the **complete local inventory** — the same discovery
//! `scan --local` performs across every detected agent (skills, MCP servers,
//! hooks, rules, slash commands, subagents, installed plugins), regardless of how
//! each capability was installed — annotates each with its security score where
//! known, and invites the user to scan the ones that have never been scored.
//!
//! A score is resolvable for a capability only when it was either installed via
//! the CLI (registry → slug → live `GET /items/{slug}`) **or** previously scanned
//! (the local scan cache, [`crate::core::scan_cache`], keyed by a CLI-side content
//! hash of the capability's bytes). There is no backend score-by-hash lookup and
//! a catalog slug can't be reconstructed locally, so an un-installed,
//! never-scanned capability has no score until the user scans it.
//!
//! On a TTY (not `--json`/`--quiet`/`--non-interactive`) the unscanned capabilities
//! trigger an inline `scan --local` offer; on accept it scans, then re-renders the
//! list from the freshly populated cache. Otherwise a command hint is printed.

use std::io::IsTerminal;
use std::path::PathBuf;

use crate::agents::enumerate;
use crate::agents::{detect_all, Scope};
use crate::api::dto::Tier;
use crate::api::Api;
use crate::cli::color;
use crate::cli::output::OutputConfig;
use crate::cli::{Interaction, ListArgs};
use crate::commands::{report, scan};
use crate::core::config::{contract_home, Config};
use crate::core::error::SsError;
use crate::core::{registry, scan_cache};

/// Run `list`.
pub async fn run_list(
    _args: &ListArgs,
    inter: Interaction,
    output: &OutputConfig,
) -> Result<(), SsError> {
    let config = Config::load()?;
    let api = Api::new(config.api_base(None))?;

    let inventory = build_inventory(&api).await?;

    if inventory.is_empty() {
        if output.is_json() {
            output.print_json(&serde_json::json!({ "data": [], "unscanned": 0 }));
        } else {
            output.print_info("No installed capabilities found across your agents.");
            output.print_substep("Scan your whole setup with `saferskills scan --local`.");
        }
        return Ok(());
    }

    if output.is_json() {
        output.print_json(&inventory_json(&inventory));
        return Ok(());
    }

    render_human(output, &inventory);

    let unscanned = inventory
        .iter()
        .filter(|e| matches!(e.resolved, Resolved::NotScanned))
        .count();
    if unscanned == 0 {
        return Ok(());
    }

    // Invite: an interactive TTY offers an inline scan + re-render; any
    // non-interactive surface falls back to a printed command hint.
    if can_prompt(inter, output) && confirm_scan(unscanned) {
        scan::run_local_audit(&api, output, "public", false).await?;
        // The cache is now populated — re-render with the fresh scores.
        let inventory = build_inventory(&api).await?;
        output.print_info("");
        render_human(output, &inventory);
    } else {
        print_scan_hint(output, unscanned);
    }
    Ok(())
}

// ─── inventory model ─────────────────────────────────────────────────────────

/// How a capability's score was resolved (or that it has none).
enum Resolved {
    /// Installed via the CLI — live current score + the install-time `seen_score`
    /// for the drift line.
    Installed {
        score: Option<u8>,
        tier: Tier,
        seen_score: Option<u8>,
    },
    /// Found in the local scan cache (previously scanned).
    Scanned {
        score: u8,
        tier: Tier,
        scanned_at: chrono::DateTime<chrono::Utc>,
        slug: String,
    },
    /// Neither installed via the CLI nor previously scanned.
    NotScanned,
}

/// One row of the local inventory — one per discovered [`LocalCapability`] (so
/// the same capability under two agents is two rows, matching `scan --local`'s
/// per-agent fan-out).
struct InventoryEntry {
    /// Backend snake_case kind (`skill` | `mcp_server` | …).
    kind: String,
    name: String,
    /// The single canonical agent id this capability lives under.
    agent: String,
    /// Real on-disk origin (display + `--json`).
    origin: PathBuf,
    /// CLI-side content hash — the scan-cache join key.
    content_hash: String,
    resolved: Resolved,
}

/// Discover the full local inventory and resolve each capability's score.
async fn build_inventory(api: &Api) -> Result<Vec<InventoryEntry>, SsError> {
    let agents = detect_all(Scope::Global);
    let enm = enumerate::enumerate_from(&agents);
    let records = registry::load()?;
    let cache = scan_cache::load()?;

    let mut entries: Vec<InventoryEntry> = Vec::new();
    for cap in &enm.capabilities {
        let kind = cap.kind.as_str().to_string();
        let agent = cap.agent.as_str().to_string();
        let content_hash = cap.content_hash();

        let resolved = if let Some(rec) = records
            .iter()
            .find(|r| r.kind == kind && r.name == cap.name && r.agents.iter().any(|a| a == &agent))
        {
            let (score, tier) = fetch_current(api, &rec.slug).await;
            Resolved::Installed {
                score,
                tier,
                seen_score: rec.seen_score,
            }
        } else if let Some(c) = cache.iter().find(|c| c.content_hash == content_hash) {
            Resolved::Scanned {
                score: c.score,
                tier: c.tier,
                scanned_at: c.scanned_at,
                slug: c.catalog_slug.clone(),
            }
        } else {
            Resolved::NotScanned
        };

        entries.push(InventoryEntry {
            kind,
            name: cap.name.clone(),
            agent,
            origin: cap.origin.clone(),
            content_hash,
            resolved,
        });
    }

    entries.sort_by(|a, b| {
        a.kind
            .cmp(&b.kind)
            .then_with(|| a.name.cmp(&b.name))
            .then_with(|| a.agent.cmp(&b.agent))
    });
    Ok(entries)
}

/// Best-effort current score for an installed capability. Offline / missing → no
/// score (the renderer falls back to the install-time `seen_score`).
async fn fetch_current(api: &Api, slug: &str) -> (Option<u8>, Tier) {
    match api.get_item(slug).await {
        Ok(d) => (
            d.item
                .latest_scan_score
                .or_else(|| d.latest_scan.as_ref().map(|s| s.aggregate_score)),
            d.item
                .latest_scan_tier
                .or_else(|| d.latest_scan.as_ref().map(|s| s.tier))
                .unwrap_or(Tier::Unscoped),
        ),
        Err(_) => (None, Tier::Unknown),
    }
}

// ─── rendering ───────────────────────────────────────────────────────────────

const KIND_W: usize = 6;
const SCORE_W: usize = 7;
const STATUS_W: usize = 14;
const WHEN_W: usize = 8;

/// Render the inventory as an aligned table: `NAME KIND AGENT SCORE STATUS WHEN
/// PATH`. Column widths for the variable cells (name / agent) are sized to the
/// data; the score band + tier color are preserved on the padded cells.
fn render_human(output: &OutputConfig, entries: &[InventoryEntry]) {
    let c = output.color;
    let name_w = entries
        .iter()
        .map(|e| e.name.chars().count())
        .max()
        .unwrap_or(4)
        .clamp(12, 32);
    let agent_w = entries
        .iter()
        .map(|e| e.agent.chars().count())
        .max()
        .unwrap_or(5)
        .clamp(6, 14);

    output.print_info(&color::dim(
        &format!(
            "{}  {}  {}  {}  {}  {}  {}",
            report::pad("NAME", name_w),
            report::pad("KIND", KIND_W),
            report::pad("AGENT", agent_w),
            lpad("SCORE", SCORE_W),
            report::pad("STATUS", STATUS_W),
            report::pad("WHEN", WHEN_W),
            "PATH",
        ),
        c,
    ));

    for e in entries {
        let name = color::bold(&report::pad(&truncate(&e.name, name_w), name_w), c);
        let kind = color::dim(&report::pad(report::kind_label(&e.kind), KIND_W), c);
        let agent = color::dim(&report::pad(&e.agent, agent_w), c);
        let path = color::dim(&contract_home(&e.origin), c);

        let (score, status, when, drift) = match &e.resolved {
            Resolved::Installed {
                score,
                tier,
                seen_score,
            } => {
                let drift = match (*seen_score, *score) {
                    (Some(seen), Some(now)) if now < seen => Some(format!(
                        "{} score dropped {seen}→{now} since install",
                        color::warn_glyph(c)
                    )),
                    _ => None,
                };
                (
                    score_band_cell(score.or(*seen_score), c),
                    tier_status(*tier, c),
                    report::pad("", WHEN_W),
                    drift,
                )
            }
            Resolved::Scanned {
                score,
                tier,
                scanned_at,
                ..
            } => (
                score_band_cell(Some(*score), c),
                tier_status(*tier, c),
                color::dim(&report::pad(&humanize_ago(*scanned_at), WHEN_W), c),
                None,
            ),
            Resolved::NotScanned => (
                color::dim(&lpad("\u{2014}", SCORE_W), c),
                color::dim(&report::pad("\u{25cb} not scanned", STATUS_W), c),
                report::pad("", WHEN_W),
                None,
            ),
        };

        output.print_info(&format!(
            "{name}  {kind}  {agent}  {score}  {status}  {when}  {path}"
        ));
        if let Some(d) = drift {
            output.print_info(&color::dim(&format!("{}  {d}", " ".repeat(name_w)), c));
        }
    }
}

/// `NN/100`, or `—` when there is no score.
fn score_cell(score: Option<u8>) -> String {
    score
        .map(|v| format!("{v}/100"))
        .unwrap_or_else(|| "\u{2014}".into())
}

/// A right-aligned, score-band-colored `NN/100` cell (dim `—` when absent).
fn score_band_cell(score: Option<u8>, c: bool) -> String {
    let txt = lpad(&score_cell(score), SCORE_W);
    match score {
        Some(v) => color::score_paint(v, &txt, c),
        None => color::dim(&txt, c),
    }
}

/// A tier marker (`● Green`) padded to [`STATUS_W`] and tier-colored.
fn tier_status(tier: Tier, c: bool) -> String {
    let plain = format!("\u{25cf} {}", tier.label());
    color::tier_paint(tier, &report::pad(&plain, STATUS_W), c)
}

/// Left-pad `s` to `w` display columns (char count).
fn lpad(s: &str, w: usize) -> String {
    let n = s.chars().count();
    if n >= w {
        s.to_string()
    } else {
        format!("{}{s}", " ".repeat(w - n))
    }
}

/// Truncate `s` to `w` display columns, ending in `…` when cut.
fn truncate(s: &str, w: usize) -> String {
    let n = s.chars().count();
    if n <= w {
        s.to_string()
    } else {
        let cut: String = s.chars().take(w.saturating_sub(1)).collect();
        format!("{cut}\u{2026}")
    }
}

fn print_scan_hint(output: &OutputConfig, unscanned: usize) {
    output.print_info("");
    output.print_info(&format!(
        "{unscanned} capability(ies) not scanned. Run: saferskills scan --local",
    ));
}

// ─── invite prompt ───────────────────────────────────────────────────────────

/// Whether an interactive scan offer may be shown — a real TTY and none of the
/// non-interactive suppressors (mirrors `commands::audit`).
fn can_prompt(inter: Interaction, output: &OutputConfig) -> bool {
    !inter.non_interactive
        && !output.is_json()
        && !output.is_quiet()
        && std::io::stderr().is_terminal()
}

/// Prompt to scan the unscanned capabilities now (default yes). A prompt error
/// (e.g. EOF) is treated as "no".
fn confirm_scan(unscanned: usize) -> bool {
    inquire::Confirm::new(&format!(
        "{unscanned} capabilities not scanned — scan them now?"
    ))
    .with_default(true)
    .prompt()
    .unwrap_or(false)
}

// ─── JSON + time helpers ─────────────────────────────────────────────────────

fn inventory_json(entries: &[InventoryEntry]) -> serde_json::Value {
    let data: Vec<serde_json::Value> = entries
        .iter()
        .map(|e| {
            let scanned = !matches!(e.resolved, Resolved::NotScanned);
            let mut o = serde_json::json!({
                "name": e.name,
                "kind": e.kind,
                "agents": [e.agent],
                "origin": e.origin.to_string_lossy(),
                "content_hash": e.content_hash,
                "scanned": scanned,
            });
            match &e.resolved {
                Resolved::Installed { score, tier, .. } => {
                    o["score"] = serde_json::json!(score);
                    o["tier"] = serde_json::json!(tier);
                }
                Resolved::Scanned {
                    score,
                    tier,
                    scanned_at,
                    slug,
                } => {
                    o["slug"] = serde_json::json!(slug);
                    o["score"] = serde_json::json!(score);
                    o["tier"] = serde_json::json!(tier);
                    o["scanned_at"] = serde_json::json!(scanned_at);
                }
                Resolved::NotScanned => {}
            }
            o
        })
        .collect();
    let unscanned = entries
        .iter()
        .filter(|e| matches!(e.resolved, Resolved::NotScanned))
        .count();
    serde_json::json!({ "data": data, "unscanned": unscanned })
}

/// A compact "time since" label (`just now` / `5m ago` / `3h ago` / `2d ago`).
fn humanize_ago(then: chrono::DateTime<chrono::Utc>) -> String {
    humanize_ago_from(chrono::Utc::now(), then)
}

fn humanize_ago_from(
    now: chrono::DateTime<chrono::Utc>,
    then: chrono::DateTime<chrono::Utc>,
) -> String {
    let secs = (now - then).num_seconds().max(0);
    if secs < 60 {
        "just now".to_string()
    } else if secs < 3600 {
        format!("{}m ago", secs / 60)
    } else if secs < 86_400 {
        format!("{}h ago", secs / 3600)
    } else {
        format!("{}d ago", secs / 86_400)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entry(kind: &str, name: &str, resolved: Resolved) -> InventoryEntry {
        InventoryEntry {
            kind: kind.into(),
            name: name.into(),
            agent: "claude-code".into(),
            origin: PathBuf::from("/x"),
            content_hash: "h".into(),
            resolved,
        }
    }

    #[test]
    fn score_cell_renders_dash_when_absent() {
        assert_eq!(score_cell(Some(91)), "91/100");
        assert_eq!(score_cell(None), "\u{2014}");
    }

    #[test]
    fn lpad_right_aligns() {
        assert_eq!(lpad("91/100", 7), " 91/100");
        assert_eq!(lpad("100/100", 7), "100/100"); // exact fit, no pad
        assert_eq!(lpad("toolong", 3), "toolong"); // never truncates
    }

    #[test]
    fn truncate_adds_ellipsis_only_when_cut() {
        assert_eq!(truncate("short", 10), "short");
        assert_eq!(truncate("abcdefghij", 5), "abcd\u{2026}");
    }

    #[test]
    fn humanize_ago_buckets() {
        let base = chrono::DateTime::from_timestamp(1_000_000_000, 0).unwrap();
        assert_eq!(humanize_ago_from(base, base), "just now");
        assert_eq!(
            humanize_ago_from(base + chrono::Duration::seconds(120), base),
            "2m ago"
        );
        assert_eq!(
            humanize_ago_from(base + chrono::Duration::hours(5), base),
            "5h ago"
        );
        assert_eq!(
            humanize_ago_from(base + chrono::Duration::days(3), base),
            "3d ago"
        );
    }

    #[test]
    fn inventory_json_shape_marks_scanned_and_counts_unscanned() {
        let entries = vec![
            entry(
                "skill",
                "scored",
                Resolved::Scanned {
                    score: 88,
                    tier: Tier::Green,
                    scanned_at: chrono::DateTime::from_timestamp(0, 0).unwrap(),
                    slug: "upload--abcd1234--skill-scored".into(),
                },
            ),
            entry("mcp_server", "fresh", Resolved::NotScanned),
        ];
        let v = inventory_json(&entries);
        assert_eq!(v["unscanned"], 1);
        let data = v["data"].as_array().unwrap();
        assert_eq!(data.len(), 2);
        // Scanned row carries score/tier/slug/scanned_at + scanned=true.
        let scored = data.iter().find(|d| d["name"] == "scored").unwrap();
        assert_eq!(scored["scanned"], true);
        assert_eq!(scored["score"], 88);
        assert_eq!(scored["tier"], "green");
        assert_eq!(scored["slug"], "upload--abcd1234--skill-scored");
        assert!(scored["scanned_at"].is_string());
        assert_eq!(scored["agents"].as_array().unwrap().len(), 1);
        // NotScanned row: scanned=false, no score key.
        let fresh = data.iter().find(|d| d["name"] == "fresh").unwrap();
        assert_eq!(fresh["scanned"], false);
        assert!(fresh["score"].is_null());
    }

    #[test]
    fn installed_json_carries_score_without_scanned_at() {
        let entries = vec![entry(
            "skill",
            "inst",
            Resolved::Installed {
                score: Some(72),
                tier: Tier::Yellow,
                seen_score: Some(80),
            },
        )];
        let v = inventory_json(&entries);
        let d = &v["data"][0];
        assert_eq!(d["scanned"], true);
        assert_eq!(d["score"], 72);
        assert_eq!(d["tier"], "yellow");
        assert!(d["scanned_at"].is_null());
    }
}
