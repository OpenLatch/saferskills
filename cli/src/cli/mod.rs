//! Command-line surface: the clap tree, global flags, and output-config
//! resolution (D-05-03, D-05-11, D-05-18).

pub mod color;
pub mod header;
pub mod output;

use clap::{Parser, Subcommand};

use crate::cli::color::ColorChoice;
use crate::cli::output::{OutputConfig, OutputFormat};

/// `saferskills` — every AI capability, independently scanned.
#[derive(Debug, Parser)]
#[command(
    name = "saferskills",
    version,
    about = "Every AI capability, independently scanned.",
    after_help = "An OpenLatch project · https://saferskills.ai",
    disable_help_subcommand = true
)]
pub struct Cli {
    #[command(subcommand)]
    pub command: Option<Commands>,

    /// Output format.
    #[arg(long, global = true, value_enum, default_value_t = OutputFormat::Human)]
    pub format: OutputFormat,

    /// Emit machine-readable JSON on stdout (implies --format json, no color,
    /// non-interactive).
    #[arg(long, global = true)]
    pub json: bool,

    /// Disable ANSI color.
    #[arg(long, global = true)]
    pub no_color: bool,

    /// Color choice (overrides NO_COLOR / TTY detection).
    #[arg(long, global = true, value_enum)]
    pub color: Option<ColorChoice>,

    /// Verbose output (full finding lists, cause chains).
    #[arg(long, short, global = true)]
    pub verbose: bool,

    /// Suppress non-essential human output.
    #[arg(long, short, global = true)]
    pub quiet: bool,

    /// Assume "yes" for confirmations up to `high` severity.
    #[arg(long, global = true)]
    pub yes: bool,

    /// Override safety gates, including the critical type-name confirm.
    #[arg(long, global = true)]
    pub force: bool,

    /// Never prompt; fail fast naming the flag needed.
    #[arg(long = "non-interactive", visible_alias = "no-input", global = true)]
    pub non_interactive: bool,
}

/// The top-level command grammar.
#[derive(Debug, Subcommand)]
pub enum Commands {
    /// Show an item's SaferSkills score + findings without installing.
    #[command(visible_alias = "check")]
    Info(InfoArgs),

    /// Install a Skill or MCP server to your detected agents.
    Install(InstallArgs),

    /// Remove a previously installed capability.
    Uninstall(UninstallArgs),

    /// Update installed capabilities.
    Update(UpdateArgs),

    /// List installed capabilities with current scores.
    List(ListArgs),

    /// Search the catalog interactively (or headless with --json), then install.
    #[command(visible_alias = "find")]
    Search(SearchArgs),

    /// Scan a local path or GitHub URL — with no target, audit everything installed.
    Scan(ScanArgs),

    /// Diagnose the local install state.
    Doctor(DoctorArgs),

    /// Generate a shell completion script.
    Completion {
        /// Target shell.
        shell: clap_complete::Shell,
    },

    /// Generate the troff man page (for packaging).
    #[command(hide = true)]
    Man,
}

/// `info <name>` — show a capability's score + findings.
#[derive(Debug, clap::Args)]
pub struct InfoArgs {
    /// Catalog item name (resolved via `?q=` + did-you-mean).
    pub name: String,

    /// Restrict resolution to a capability kind (e.g. `skill`, `mcp_server`).
    #[arg(long)]
    pub kind: Option<String>,
}

/// `install <name>` — install a capability to your detected agents.
#[derive(Debug, clap::Args)]
pub struct InstallArgs {
    /// Catalog item name.
    pub name: String,

    /// Install only to these agents (repeatable). Canonical ids.
    #[arg(long = "to")]
    pub to: Vec<String>,

    /// Install to every detected agent without prompting.
    #[arg(long)]
    pub all: bool,

    /// Write the repo-local config instead of the global one.
    #[arg(long)]
    pub project: bool,

    /// On a registry collision, update in place.
    #[arg(long)]
    pub update: bool,

    /// On a registry collision, reinstall from scratch.
    #[arg(long)]
    pub reinstall: bool,

    /// The score the user saw, for install-time drift re-prompt.
    #[arg(long = "seen-score")]
    pub seen_score: Option<u8>,

    /// Resolve + plan but write nothing.
    #[arg(long = "dry-run")]
    pub dry_run: bool,
}

/// `uninstall <name>`.
#[derive(Debug, clap::Args)]
pub struct UninstallArgs {
    /// Catalog item name.
    pub name: String,

    /// Only uninstall from this agent (canonical id); default removes from all.
    #[arg(long = "from")]
    pub from: Option<String>,
}

/// `update [name] [--all]`.
#[derive(Debug, clap::Args)]
pub struct UpdateArgs {
    /// A specific item to update (omit with `--all`).
    pub name: Option<String>,

    /// Update every installed item.
    #[arg(long)]
    pub all: bool,

    /// Non-interactively uninstall items that dropped to Red.
    #[arg(long = "prune-red")]
    pub prune_red: bool,
}

/// `list`.
#[derive(Debug, clap::Args)]
pub struct ListArgs {}

/// Catalog sort key — a thin clap mirror of the server's `SortKey`. The
/// `#[value(name = …)]` names are the exact snake_case query values the API
/// accepts, so [`SortArg::as_server_key`] is a passthrough.
#[derive(Debug, Clone, Copy, PartialEq, Eq, clap::ValueEnum)]
pub enum SortArg {
    /// Most installed (the trending default).
    #[value(name = "most_installed")]
    MostInstalled,
    /// Fewest installs.
    #[value(name = "least_installed")]
    LeastInstalled,
    /// Most recently added/updated.
    #[value(name = "recent")]
    Recent,
    /// Oldest first.
    #[value(name = "oldest")]
    Oldest,
    /// Highest security score first.
    #[value(name = "highest_score")]
    HighestScore,
    /// Lowest security score first.
    #[value(name = "lowest_score")]
    LowestScore,
    /// Most GitHub stars.
    #[value(name = "most_starred")]
    MostStarred,
    /// Name A→Z.
    #[value(name = "name_asc")]
    NameAsc,
    /// Name Z→A.
    #[value(name = "name_desc")]
    NameDesc,
    /// Most install activity (trailing quarter).
    #[value(name = "most_active")]
    MostActive,
    /// Least install activity.
    #[value(name = "least_active")]
    LeastActive,
}

impl SortArg {
    /// The exact server query value.
    pub fn as_server_key(self) -> &'static str {
        match self {
            SortArg::MostInstalled => "most_installed",
            SortArg::LeastInstalled => "least_installed",
            SortArg::Recent => "recent",
            SortArg::Oldest => "oldest",
            SortArg::HighestScore => "highest_score",
            SortArg::LowestScore => "lowest_score",
            SortArg::MostStarred => "most_starred",
            SortArg::NameAsc => "name_asc",
            SortArg::NameDesc => "name_desc",
            SortArg::MostActive => "most_active",
            SortArg::LeastActive => "least_active",
        }
    }
}

/// `search [query]` — interactive faceted catalog finder + installer (alias
/// `find`). With `--json` (or any non-TTY context) it runs headless: one fetch,
/// the catalog envelope printed as JSON to stdout, no TUI.
#[derive(Debug, clap::Args)]
pub struct SearchArgs {
    /// Seed query (FTS + fuzzy). Omit for the trending list.
    pub query: Option<String>,

    /// Restrict to these capability kinds (repeatable): `skill`, `mcp_server`,
    /// `hook`, `plugin`, `rules`.
    #[arg(long = "kind")]
    pub kind: Vec<String>,

    /// Restrict to these agent compatibilities (repeatable; canonical ids).
    #[arg(long = "agent")]
    pub agent: Vec<String>,

    /// Restrict to these scan tiers (repeatable): `green`, `yellow`, `orange`,
    /// `red`.
    #[arg(long = "scan-tier")]
    pub scan_tier: Vec<String>,

    /// Minimum aggregate score (0–100).
    #[arg(long = "score-min", value_parser = clap::value_parser!(u8).range(0..=100))]
    pub score_min: Option<u8>,

    /// Sort key (default: most_installed — trending).
    #[arg(long, value_enum)]
    pub sort: Option<SortArg>,

    /// Page size (1–100; default 50).
    #[arg(long, default_value_t = 50, value_parser = clap::value_parser!(u32).range(1..=100))]
    pub limit: u32,

    /// Include low/empty quality_tier items (default hides them).
    #[arg(long = "show-low-quality")]
    pub show_low_quality: bool,
}

/// `scan [target]`.
#[derive(Debug, clap::Args)]
pub struct ScanArgs {
    /// A local path or a GitHub URL. Omit to audit every installed capability.
    pub target: Option<String>,

    /// Scan every installed capability across detected agents (the default when
    /// no target is given).
    #[arg(long)]
    pub local: bool,

    /// Keep the scan unlisted (token URL + expiry).
    #[arg(long)]
    pub private: bool,

    /// Expand the per-capability 5-axis breakdown + inline critical/high
    /// findings (the default report stays concise).
    #[arg(long)]
    pub detailed: bool,
}

/// `doctor`.
#[derive(Debug, clap::Args)]
pub struct DoctorArgs {
    /// Re-apply any registry-vs-filesystem drift found (repair).
    #[arg(long)]
    pub fix: bool,
}

/// The resolved global interaction flags threaded into the gating commands
/// (`install` / `uninstall` / `update` / `doctor`), per D-05-21.
#[derive(Debug, Clone, Copy)]
pub struct Interaction {
    /// Assume "yes" for confirmations up to `high` severity.
    pub yes: bool,
    /// Override every gate, including the critical type-name confirm.
    pub force: bool,
    /// Never prompt; fail fast naming the flag needed (also implied by --json).
    pub non_interactive: bool,
}

/// Resolve the interaction flags from the parsed CLI (`--json` ⇒ non-interactive).
pub fn interaction(cli: &Cli) -> Interaction {
    Interaction {
        yes: cli.yes,
        force: cli.force,
        non_interactive: cli.non_interactive || cli.json,
    }
}

/// Resolve the output configuration from parsed flags (D-05-11). `--json`
/// forces Json format AND disables color (machine output is never colorized).
pub fn build_output_config(cli: &Cli) -> OutputConfig {
    let format = if cli.json {
        OutputFormat::Json
    } else {
        cli.format
    };
    let color = if format == OutputFormat::Json {
        false
    } else {
        color::is_color_enabled(cli.color, cli.no_color)
    };
    OutputConfig {
        format,
        verbose: cli.verbose,
        quiet: cli.quiet,
        color,
    }
}

/// Map a parsed command to its stable telemetry label `(command, subcommand)`
/// — drawn from the grammar, never from flag values (D-05-13).
pub fn command_label(cmd: &Commands) -> (&'static str, Option<&'static str>) {
    match cmd {
        Commands::Info(_) => ("info", None),
        Commands::Install(_) => ("install", None),
        Commands::Uninstall(_) => ("uninstall", None),
        Commands::Update(_) => ("update", None),
        Commands::List(_) => ("list", None),
        Commands::Search(_) => ("search", None),
        Commands::Scan(_) => ("scan", None),
        Commands::Doctor(_) => ("doctor", None),
        Commands::Completion { .. } => ("completion", None),
        Commands::Man => ("man", None),
    }
}

/// Known top-level subcommands for the did-you-mean suggester.
pub const KNOWN_SUBCOMMANDS: &[&str] = &[
    "info",
    "check",
    "install",
    "uninstall",
    "update",
    "list",
    "search",
    "find",
    "scan",
    "doctor",
    "completion",
];

/// Suggest the closest known subcommand for an unknown input (jaro_winkler >
/// 0.7). Complements clap's own "did you mean".
pub fn suggest_subcommand(input: &str) -> Option<String> {
    let lower = input.to_ascii_lowercase();
    KNOWN_SUBCOMMANDS
        .iter()
        .map(|c| (*c, strsim::jaro_winkler(&lower, c)))
        .filter(|(_, score)| *score > 0.7)
        .max_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal))
        .map(|(c, _)| c.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use clap::CommandFactory;

    #[test]
    fn cli_definition_is_valid() {
        // Panics at test time if the derive produces an inconsistent command
        // tree (duplicate args, bad alias, etc.).
        Cli::command().debug_assert();
    }

    #[test]
    fn json_flag_forces_json_and_no_color() {
        let cli = Cli::parse_from(["saferskills", "--json", "info", "x"]);
        let cfg = build_output_config(&cli);
        assert!(cfg.is_json());
        assert!(!cfg.color);
    }

    #[test]
    fn info_has_check_alias() {
        let cli = Cli::parse_from(["saferskills", "check", "github-mcp"]);
        assert!(matches!(cli.command, Some(Commands::Info(_))));
    }

    #[test]
    fn suggest_subcommand_finds_close_typo() {
        assert_eq!(suggest_subcommand("instal").as_deref(), Some("install"));
        assert_eq!(suggest_subcommand("info").as_deref(), Some("info"));
        assert!(suggest_subcommand("zzzzzz").is_none());
    }

    #[test]
    fn command_label_from_grammar() {
        let cli = Cli::parse_from(["saferskills", "update", "--all"]);
        assert_eq!(
            command_label(cli.command.as_ref().unwrap()),
            ("update", None)
        );
    }
}
