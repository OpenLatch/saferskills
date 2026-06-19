// The SaferSkills CLI is interactive, so it keeps the default `console`
// subsystem on Windows (unlike openlatch-client's daemon, which uses the
// `windows` subsystem to avoid a console window on service launch). The
// explicit attribute documents the intent; `AttachConsole(ATTACH_PARENT_
// PROCESS)` below reattaches stdio if the process was spawned without one.
#![cfg_attr(all(windows, not(debug_assertions)), windows_subsystem = "console")]

use clap::{CommandFactory, Parser};

use saferskills::cli::output::OutputConfig;
use saferskills::cli::{self, Cli, Commands};
use saferskills::commands;
use saferskills::core::config::Config;
use saferskills::core::crash_report;
use saferskills::core::error::SsError;
use saferskills::core::telemetry;

#[cfg(windows)]
fn attach_parent_console_if_any() {
    use winapi::um::wincon::{AttachConsole, ATTACH_PARENT_PROCESS};
    // SAFETY: FFI call with a well-known constant; returns 0 (ignored) when
    // there is no parent console to attach to.
    unsafe {
        let _ = AttachConsole(ATTACH_PARENT_PROCESS);
    }
}

#[cfg(not(windows))]
fn attach_parent_console_if_any() {}

fn main() {
    attach_parent_console_if_any();

    // Crash reporting first — captures panics in everything below, including the
    // tokio runtime construction and clap parsing. The guard is bound to main's
    // stack so its Drop (2s flush) runs on normal exit. A hard no-op when the
    // `crash-report` feature is off, no DSN is baked, or consent resolves to
    // disabled (opt-out env / `[crashreport] enabled = false`).
    let _crash_guard = crash_report::init();
    // Chain our panic hook onto sentry's (which init installed under unwind).
    crash_report::install_panic_hook();

    // SIGINT → exit 130. Flush pending crash reports first —
    // `process::exit` skips Drop impls, so the guard's flush-on-drop never runs.
    // The single PostHog `command_invoked` event is sent at the end of a normal
    // run (not buffered), so there is nothing to lose there on interrupt.
    let _ = ctrlc::set_handler(|| {
        // Restore the terminal first if a TUI (`search`) owns it — `process::exit`
        // skips every Drop, including the RAII TerminalGuard. A hard no-op for
        // every non-TUI command (the ACTIVE flag is unset).
        saferskills::tui::terminal::restore_on_signal();
        crash_report::flush(std::time::Duration::from_secs(2));
        std::process::exit(130);
    });

    let exit_code = match tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
    {
        Ok(rt) => rt.block_on(run()),
        Err(e) => {
            eprintln!("Error: failed to start async runtime: {e} (SS-E-9999)");
            1
        }
    };
    std::process::exit(exit_code);
}

/// Parse, dispatch, emit telemetry, and map the result to an exit code.
async fn run() -> i32 {
    let cli = Cli::parse();
    let output = cli::build_output_config(&cli);
    let inter = cli::interaction(&cli);

    // Banner first, on every invocation — except the machine-output commands
    // (`completion`/`man`) whose stdout is captured into shell rc files or
    // packaging, where a per-shell-startup banner would be noise. The colour is
    // picked fresh each run; `header::print` self-suppresses in Json / quiet.
    let machine_output = matches!(
        cli.command,
        Some(Commands::Completion { .. }) | Some(Commands::Man)
    );
    if !machine_output {
        cli::header::print(&output);
    }

    // Usage analytics (PostHog): asked once on the first interactive launch and
    // stored in config; env opt-outs (CI / DO_NOT_TRACK / SAFERSKILLS_NO_TELEMETRY)
    // and a build with no baked key keep it silently off. Machine-output commands
    // and every non-interactive context never prompt.
    let config = Config::load().unwrap_or_default();
    let telemetry_on = telemetry::is_enabled(telemetry::resolve_telemetry_consent(
        &output,
        &config,
        inter.non_interactive || machine_output,
    ));

    // No subcommand → banner (already printed above) + help, exit 0.
    let Some(command) = cli.command.as_ref() else {
        let _ = Cli::command().print_help();
        return 0;
    };

    let (cmd_label, sub_label) = cli::command_label(command);
    // Tag the Sentry scope with the closed-enum command grammar (never a flag
    // value) so a panic carries the command that triggered it. No-op when crash
    // reporting is disabled.
    crash_report::enrich_cli_scope(cmd_label, sub_label);
    let started = std::time::Instant::now();

    // First-launch security audit: a one-time opt-in offer to scan
    // everything already installed. Fail-open + persisted, so it never re-prompts
    // and never affects the user's command outcome. Calls run_scan directly (no
    // dispatch recursion).
    commands::audit::maybe_first_run_audit(inter, &output).await;

    let result = dispatch(command, inter, &output).await;
    let exit_code = match &result {
        Ok(()) => 0,
        Err(e) => e.exit_code(),
    };

    let duration_ms = started.elapsed().as_millis().min(u128::from(u64::MAX)) as u64;
    telemetry::capture_command_invoked(cmd_label, sub_label, exit_code, duration_ms, telemetry_on)
        .await;

    if let Err(e) = result {
        // `--verbose` (human) renders the fancy miette diagnostic boundary;
        // otherwise the OutputConfig printer (human multi-line or JSON).
        if output.verbose && !output.is_json() {
            eprintln!("{:?}", miette::Report::new(e));
        } else {
            output.print_error(&e);
        }
    }
    exit_code
}

/// Single `match` over the clap enum → one free `run_*` fn per command. The
/// gating commands (install/uninstall/update/doctor) also receive the resolved
/// interaction flags.
async fn dispatch(
    command: &Commands,
    inter: cli::Interaction,
    output: &OutputConfig,
) -> Result<(), SsError> {
    match command {
        Commands::Info(args) => commands::info::run_info(args, output).await,
        Commands::Install(args) => commands::install::run_install(args, inter, output).await,
        Commands::Uninstall(args) => commands::uninstall::run_uninstall(args, inter, output).await,
        Commands::Update(args) => commands::update::run_update(args, inter, output).await,
        Commands::List(args) => commands::list::run_list(args, inter, output).await,
        Commands::Search(args) => commands::search::run_search(args, inter, output).await,
        Commands::Capability(args) => commands::capability::run_capability(args, output).await,
        Commands::Agent(args) => commands::agent::run_agent(args, inter, output).await,
        Commands::Doctor(args) => commands::doctor::run_doctor(args, inter, output).await,
        Commands::Completion { shell } => commands::completion::run_completion(*shell, output),
        Commands::Man => commands::completion::run_man(output),
    }
}
