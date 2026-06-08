//! `saferskills search [query]` (alias `find`) — interactive faceted catalog
//! finder + installer, with a headless JSON fallback.
//!
//! Interactive (a real TTY, no `--json`/`--non-interactive`): launches the
//! ratatui TUI (`crate::tui::search`) — live server search, a facet sidebar,
//! multi-select, and a rich preview pane. On Enter the TUI tears down fully and
//! the marked set installs through the existing gated [`install::run_install`]
//! flow (`--all` agents, drift-armed via `seen_score`); non-installable kinds
//! (hooks/plugins/rules) are skipped with a notice + report link.
//!
//! Headless (`--json`, `--non-interactive`, or a non-TTY stdin/stderr): one
//! fetch, the catalog envelope printed as JSON to stdout, no TUI.

use std::io::IsTerminal;

use crate::api::dto::CatalogItemSummary;
use crate::api::{Api, CatalogQuery};
use crate::cli::output::OutputConfig;
use crate::cli::{InstallArgs, Interaction, SearchArgs};
use crate::commands::{install, report};
use crate::core::config::Config;
use crate::core::error::{SsError, ERR_WRITER_UNSUPPORTED};
use crate::tui::search::state::{installable_split, Facets};

/// Run `search`.
pub async fn run_search(
    args: &SearchArgs,
    inter: Interaction,
    output: &OutputConfig,
) -> Result<(), SsError> {
    let config = Config::load()?;
    let api = Api::new(config.api_base(None))?;

    if is_headless(inter, output) {
        return run_headless(&api, args, output).await;
    }

    // Interactive: launch the TUI, then install the marked set.
    let seed_query = args.query.clone().unwrap_or_default();
    let facets = seed_facets(args);
    let sort = args.sort.map(|s| s.as_server_key().to_string());
    let marked = crate::tui::search::run(
        api.clone(),
        seed_query,
        facets,
        sort,
        args.limit,
        output.color,
    )
    .await?;

    if marked.is_empty() {
        output.print_info("Nothing selected.");
        return Ok(());
    }
    install_marked(&api, inter, output, marked).await
}

/// Whether to skip the TUI and emit JSON. The TUI needs a real TTY on **both**
/// stdin (key input) and stderr (the draw surface); `--json`/`--non-interactive`
/// force headless regardless.
fn is_headless(inter: Interaction, output: &OutputConfig) -> bool {
    output.is_json()
        || inter.non_interactive
        || !std::io::stdin().is_terminal()
        || !std::io::stderr().is_terminal()
}

/// One fetch → JSON envelope on stdout. Always JSON (the headless contract,
/// D-locked) — even without `--json`.
async fn run_headless(api: &Api, args: &SearchArgs, output: &OutputConfig) -> Result<(), SsError> {
    let query = build_query(args);
    let spinner = output.create_spinner("Searching the catalog…");
    let env = api.list_items(&query).await;
    if let Some(pb) = spinner {
        pb.finish_and_clear();
    }
    let env = env?;
    output.print_json(&headless_json(&env, api.base()));
    Ok(())
}

/// Build the API query from the parsed args (headless path).
fn build_query(args: &SearchArgs) -> CatalogQuery {
    CatalogQuery {
        q: args.query.clone(),
        kinds: args.kind.clone(),
        agents: args.agent.clone(),
        scan_tiers: args.scan_tier.clone(),
        score_min: args.score_min,
        sort: args.sort.map(|s| s.as_server_key().to_string()),
        limit: args.limit,
        show_low_quality: args.show_low_quality,
    }
}

/// The seed facet state for the interactive TUI (mirrors [`build_query`]).
fn seed_facets(args: &SearchArgs) -> Facets {
    Facets {
        kinds: args.kind.clone(),
        agents: args.agent.clone(),
        scan_tiers: args.scan_tier.clone(),
        min_score: args.score_min.unwrap_or(0),
        show_low_quality: args.show_low_quality,
    }
}

/// The jq-friendly headless payload: a trimmed catalog row list + the totals.
fn headless_json(env: &crate::api::dto::CatalogListEnvelope, base: &str) -> serde_json::Value {
    let data: Vec<serde_json::Value> = env
        .data
        .iter()
        .map(|i| {
            serde_json::json!({
                "slug": i.slug,
                "name": i.display_name,
                "kind": i.kind,
                "score": i.latest_scan_score,
                "tier": i.latest_scan_tier,
                "popularity_score": i.popularity_score,
                "installable": is_installable(i),
                "report_url": format!("{base}/items/{}", i.slug),
            })
        })
        .collect();
    serde_json::json!({
        "data": data,
        "total_count": env.total_count,
        "truncated": env.total_count > env.data.len() as i64,
    })
}

fn is_installable(item: &CatalogItemSummary) -> bool {
    crate::tui::search::state::is_installable_kind(&item.kind)
}

/// Install the marked set through the existing gated flow. Non-installable kinds
/// (hooks/plugins/rules) are skipped with a notice + report link. Any single
/// install failure is reported but the rest continue; if any failed the command
/// exits non-zero.
async fn install_marked(
    api: &Api,
    inter: Interaction,
    output: &OutputConfig,
    marked: Vec<CatalogItemSummary>,
) -> Result<(), SsError> {
    let (installable, skipped) = installable_split(&marked);

    for item in &skipped {
        output.print_warn(&format!(
            "Skipping {} ({}) — the CLI installs Skills + MCP servers only.",
            item.display_name,
            report::kind_label(&item.kind)
        ));
        output.print_substep(&format!("Report: {}/items/{}", api.base(), item.slug));
    }

    if installable.is_empty() {
        if skipped.is_empty() {
            output.print_info("Nothing to install.");
        }
        return Ok(());
    }

    let mut installed = 0usize;
    let mut failures: Vec<String> = Vec::new();
    for item in &installable {
        output.print_info("");
        output.print_step(&format!("Installing {}…", item.display_name));
        let install_args = InstallArgs {
            name: item.slug.clone(),
            to: Vec::new(),
            all: true, // auto-target every compatible detected agent (D-locked)
            project: false,
            update: false,
            reinstall: false,
            seen_score: item.latest_scan_score, // arms the install-time drift re-prompt
            dry_run: false,
        };
        match install::run_install(&install_args, inter, output).await {
            Ok(()) => installed += 1,
            Err(e) => {
                output.print_error(&e);
                failures.push(item.display_name.clone());
            }
        }
    }

    output.print_info("");
    output.print_step(&format!("Installed {installed}/{}.", installable.len()));
    if !failures.is_empty() {
        return Err(SsError::new(
            ERR_WRITER_UNSUPPORTED,
            format!("Some installs failed: {}.", failures.join(", ")),
        )
        .with_suggestion("Re-run `saferskills install <name>` for the failed items to see why."));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::api::dto::{CatalogItemSummary, CatalogListEnvelope, Tier};

    fn item(slug: &str, kind: &str, name: &str, score: Option<u8>) -> CatalogItemSummary {
        CatalogItemSummary {
            id: slug.into(),
            slug: slug.into(),
            kind: kind.into(),
            display_name: name.into(),
            description: None,
            github_url: None,
            github_org: None,
            github_repo: None,
            source_kind: None,
            popularity_tier: "emerging".into(),
            popularity_score: 1234,
            latest_scan_score: score,
            latest_scan_tier: score.map(|_| Tier::Green),
            latest_scan_at: None,
            findings_count: 0,
            registries: vec![],
            agent_compatibility: vec![],
            updated_at: None,
        }
    }

    #[test]
    fn build_query_threads_all_facets() {
        let args = SearchArgs {
            query: Some("redis".into()),
            kind: vec!["mcp_server".into()],
            agent: vec!["claude-code".into()],
            scan_tier: vec!["green".into()],
            score_min: Some(80),
            sort: Some(crate::cli::SortArg::HighestScore),
            limit: 25,
            show_low_quality: true,
        };
        let q = build_query(&args);
        assert_eq!(q.q.as_deref(), Some("redis"));
        assert_eq!(q.kinds, vec!["mcp_server".to_string()]);
        assert_eq!(q.sort.as_deref(), Some("highest_score"));
        assert_eq!(q.score_min, Some(80));
        assert!(q.show_low_quality);
    }

    #[test]
    fn seed_facets_mirror_args() {
        let args = SearchArgs {
            query: None,
            kind: vec!["skill".into()],
            agent: vec![],
            scan_tier: vec![],
            score_min: None,
            sort: None,
            limit: 50,
            show_low_quality: false,
        };
        let f = seed_facets(&args);
        assert_eq!(f.kinds, vec!["skill".to_string()]);
        assert_eq!(f.min_score, 0); // None → 0 (no filter)
        assert!(!f.show_low_quality);
    }

    #[test]
    fn headless_json_trims_rows_and_flags_truncation() {
        let env = CatalogListEnvelope {
            data: vec![
                item("a--b--skill-x", "skill", "X", Some(91)),
                item("a--b--hook-y", "hook", "Y", None),
            ],
            next_cursor: None,
            total_count: 50,
            page: 1,
            total_pages: 1,
            page_size: 2,
        };
        let v = headless_json(&env, "https://saferskills.ai");
        assert_eq!(v["total_count"], 50);
        assert_eq!(v["truncated"], true);
        let data = v["data"].as_array().unwrap();
        assert_eq!(data.len(), 2);
        assert_eq!(data[0]["slug"], "a--b--skill-x");
        assert_eq!(data[0]["score"], 91);
        assert_eq!(data[0]["installable"], true);
        assert_eq!(
            data[0]["report_url"],
            "https://saferskills.ai/items/a--b--skill-x"
        );
        // A hook is discoverable but not installable.
        assert_eq!(data[1]["installable"], false);
        assert!(data[1]["score"].is_null());
    }

    #[test]
    fn headless_json_untruncated_when_total_equals_loaded() {
        let env = CatalogListEnvelope {
            data: vec![item("a--b--skill-x", "skill", "X", Some(91))],
            next_cursor: None,
            total_count: 1,
            page: 1,
            total_pages: 1,
            page_size: 1,
        };
        let v = headless_json(&env, "https://saferskills.ai");
        assert_eq!(v["truncated"], false);
    }

    #[test]
    fn is_headless_forced_by_json_and_non_interactive() {
        let json = OutputConfig {
            format: crate::cli::output::OutputFormat::Json,
            verbose: false,
            quiet: false,
            color: false,
        };
        let inter = Interaction {
            yes: false,
            force: false,
            non_interactive: false,
        };
        // --json short-circuits to headless regardless of TTY.
        assert!(is_headless(inter, &json));
        // --non-interactive forces headless too.
        let human = OutputConfig {
            format: crate::cli::output::OutputFormat::Human,
            verbose: false,
            quiet: false,
            color: false,
        };
        let ni = Interaction {
            yes: false,
            force: false,
            non_interactive: true,
        };
        assert!(is_headless(ni, &human));
    }

    #[test]
    fn is_installable_only_skill_and_mcp() {
        assert!(is_installable(&item("a--b--skill-x", "skill", "X", None)));
        assert!(is_installable(&item(
            "a--b--mcp-server-y",
            "mcp_server",
            "Y",
            None
        )));
        assert!(!is_installable(&item("a--b--hook-z", "hook", "Z", None)));
        assert!(!is_installable(&item(
            "a--b--plugin-w",
            "plugin",
            "W",
            None
        )));
        assert!(!is_installable(&item("a--b--rules-v", "rules", "V", None)));
    }
}
