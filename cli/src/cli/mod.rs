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

    /// Assume "yes" for confirmations up to `high` severity (D-05-21; Phase B).
    #[arg(long, global = true)]
    pub yes: bool,

    /// Override safety gates, including the critical type-name confirm (D-05-21).
    #[arg(long, global = true)]
    pub force: bool,

    /// Never prompt; fail fast naming the flag needed (D-05-21).
    #[arg(long = "non-interactive", visible_alias = "no-input", global = true)]
    pub non_interactive: bool,
}

/// The command grammar. `info` + `completion` + `man` are wired in Phase A; the
/// rest are stubs returning `SS-E-1090` until Phase B/C.
#[derive(Debug, Subcommand)]
pub enum Commands {
    /// Show an item's SaferSkills score + findings without installing.
    #[command(visible_alias = "check")]
    Info(InfoArgs),

    /// Install a Skill or MCP server to your detected agents (Phase B).
    Install(InstallArgs),

    /// Remove a previously installed capability (Phase B).
    Uninstall(UninstallArgs),

    /// Update installed capabilities (Phase B).
    Update(UpdateArgs),

    /// List installed capabilities with current scores (Phase B).
    List(ListArgs),

    /// Scan a local path or GitHub URL (Phase C).
    Scan(ScanArgs),

    /// Diagnose the local install state (Phase B).
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

/// `info <name>` — the unblocked read headline.
#[derive(Debug, clap::Args)]
pub struct InfoArgs {
    /// Catalog item name (resolved via `?q=` + did-you-mean).
    pub name: String,

    /// Restrict resolution to a capability kind (e.g. `skill`, `mcp_server`).
    #[arg(long)]
    pub kind: Option<String>,
}

/// `install <name>` (Phase B). Full flag surface declared now so the binary is
/// whole and `--help` shows the real shape from day one.
#[derive(Debug, clap::Args)]
pub struct InstallArgs {
    /// Catalog item name.
    pub name: String,

    /// Install only to these agents (repeatable). Canonical ids (D-05-14).
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

    /// The score the user saw, for install-time drift re-prompt (D-05-25).
    #[arg(long = "seen-score")]
    pub seen_score: Option<u8>,

    /// Resolve + plan but write nothing.
    #[arg(long = "dry-run")]
    pub dry_run: bool,
}

/// `uninstall <name>` (Phase B).
#[derive(Debug, clap::Args)]
pub struct UninstallArgs {
    /// Catalog item name.
    pub name: String,

    /// Only uninstall from this agent (canonical id); default removes from all.
    #[arg(long = "from")]
    pub from: Option<String>,
}

/// `update [name] [--all]` (Phase B).
#[derive(Debug, clap::Args)]
pub struct UpdateArgs {
    /// A specific item to update (omit with `--all`).
    pub name: Option<String>,

    /// Update every installed item.
    #[arg(long)]
    pub all: bool,

    /// Non-interactively uninstall items that dropped to Red (D-05-23).
    #[arg(long = "prune-red")]
    pub prune_red: bool,
}

/// `list` (Phase B).
#[derive(Debug, clap::Args)]
pub struct ListArgs {}

/// `scan <target>` (Phase C).
#[derive(Debug, clap::Args)]
pub struct ScanArgs {
    /// A local path or a GitHub URL.
    pub target: Option<String>,

    /// Scan every installed capability across detected agents.
    #[arg(long)]
    pub local: bool,

    /// Keep the scan unlisted (token URL + expiry).
    #[arg(long)]
    pub private: bool,
}

/// `doctor` (Phase B).
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
