//! `saferskills doctor`.
//!
//! A diagnostic pass: API connectivity, detected agents (flagging MED/LOW
//! confidence writers), registry-vs-filesystem drift (per-writer `verify()`), and
//! local-config sanity. `--fix` re-applies any drifted record. The exit code
//! reflects the worst section.

use crate::agents::writer::{Confidence, VerifyStatus};
use crate::agents::{detect_all, writers, Scope};
use crate::api::Api;
use crate::cli::color;
use crate::cli::output::OutputConfig;
use crate::cli::{DoctorArgs, Interaction};
use crate::core::config::{cache_dir, Config};
use crate::core::error::{SsError, ERR_WRITE_ROLLBACK};
use crate::core::registry;

use super::install::{reinstall_existing, verify_record};

#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
enum Level {
    Ok,
    Warn,
    Error,
}

/// Run `doctor`.
pub async fn run_doctor(
    args: &DoctorArgs,
    inter: Interaction,
    output: &OutputConfig,
) -> Result<(), SsError> {
    let config = Config::load()?;
    let api = Api::new(config.api_base(None))?;
    let mut worst = Level::Ok;
    let mut report = serde_json::Map::new();

    // 1. Connectivity.
    match api.health().await {
        Ok(h) if h.migrations_ok => output.print_step(&format!("API reachable ({}).", h.status)),
        Ok(h) => {
            output.print_warn(&format!(
                "API degraded: {}.",
                h.migrations_error.unwrap_or_default()
            ));
            worst = worst.max(Level::Warn);
        }
        Err(e) => {
            output.print_warn(&format!("API unreachable: {}.", e.message));
            worst = worst.max(Level::Warn);
        }
    }
    report.insert(
        "connectivity_ok".into(),
        serde_json::json!(worst == Level::Ok),
    );

    // 2. Agents.
    let detected = detect_all(Scope::Global);
    if detected.is_empty() {
        output.print_warn("No supported agents detected.");
        worst = worst.max(Level::Warn);
    }
    for a in &detected {
        let writer = writers::writer_for(a.id);
        if writer.confidence() != Confidence::High {
            output.print_warn(&format!(
                "{} detected — {}-confidence writer; verify the install against your setup.",
                a.id.display_name(),
                writer.confidence().label()
            ));
            worst = worst.max(Level::Warn);
        } else {
            output.print_step(&format!("{} detected.", a.id.display_name()));
        }
    }
    report.insert(
        "agents".into(),
        serde_json::json!(detected.iter().map(|a| a.id.as_str()).collect::<Vec<_>>()),
    );

    // 3. Registry-vs-filesystem drift.
    let records = registry::load()?;
    let mut drifted: Vec<usize> = Vec::new();
    for (i, record) in records.iter().enumerate() {
        let statuses = verify_record(record);
        let has_drift = statuses.iter().any(|(_, s)| *s != VerifyStatus::Ok);
        if has_drift {
            drifted.push(i);
            worst = worst.max(Level::Warn);
            for (id, status) in &statuses {
                if *status != VerifyStatus::Ok {
                    let what = match status {
                        VerifyStatus::Missing => "entry missing",
                        VerifyStatus::Malformed => "config malformed",
                        VerifyStatus::Ok => unreachable!(),
                    };
                    output.print_warn(&format!(
                        "\"{}\" on {}: {what}.",
                        record.name,
                        id.display_name()
                    ));
                }
            }
        } else {
            output.print_step(&format!("\"{}\" is installed cleanly.", record.name));
        }
    }

    // --fix re-applies drifted records.
    if args.fix && !drifted.is_empty() {
        for i in &drifted {
            let record = &records[*i];
            output.print_substep(&format!("Re-applying \"{}\"…", record.name));
            if let Err(e) = reinstall_existing(record, inter, output).await {
                output.print_warn(&format!(
                    "Could not repair \"{}\": {}",
                    record.name, e.message
                ));
                worst = worst.max(Level::Error);
            }
        }
    } else if !drifted.is_empty() {
        output.print_info("Run `saferskills doctor --fix` to repair the drift above.");
    }
    report.insert("drifted_count".into(), serde_json::json!(drifted.len()));

    // 4. Local config sanity.
    output.print_step(&format!("Config OK · cache at {}", cache_dir().display()));

    if output.is_json() {
        output.print_json(&serde_json::Value::Object(report));
    } else {
        output.print_info("");
        match worst {
            Level::Ok => output.print_step("All checks passed."),
            Level::Warn => output.print_warn("Completed with warnings."),
            Level::Error => output.print_info(&color::red("Completed with errors.", output.color)),
        }
    }

    match worst {
        Level::Error => Err(SsError::new(
            ERR_WRITE_ROLLBACK,
            "doctor found unrepaired problems.",
        )),
        _ => Ok(()),
    }
}
