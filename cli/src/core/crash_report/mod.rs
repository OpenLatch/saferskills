//! Opt-out panic diagnostics in the dedicated SaferSkills PostHog project.
//! Usage-analytics consent remains independent. Missing baked keys disable all
//! diagnostics; the SDK hook captures panics before unwinding, with a bounded
//! flush. No panic messages, user paths or arbitrary properties leave the process.

#[cfg(feature = "crash-report")]
mod config;
#[cfg(feature = "crash-report")]
mod consent;
#[cfg(feature = "crash-report")]
mod scrub;

#[cfg(feature = "crash-report")]
mod imp {
    use std::sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, OnceLock,
    };
    use std::time::Duration;

    use crate::core::{config::config_path, telemetry::baked_key};
    use posthog_rs::{ClientOptions, ClientOptionsBuilder, ErrorTrackingOptionsBuilder};

    static ACTIVE: AtomicBool = AtomicBool::new(false);
    static COMMAND: OnceLock<(String, Option<String>)> = OnceLock::new();

    pub struct ClientInitGuard;
    impl Drop for ClientInitGuard {
        fn drop(&mut self) {
            flush(Duration::from_secs(2));
        }
    }

    /// Initialize before Tokio/clap so their panics are covered too.
    pub fn init() -> Option<ClientInitGuard> {
        if !super::consent::resolve(&config_path(), !baked_key().is_empty()).enabled() {
            return None;
        }
        let options = options(baked_key(), env!("SAFERSKILLS_POSTHOG_HOST"))?;
        posthog_rs::init_global(options).ok()?;
        ACTIVE.store(true, Ordering::Release);
        Some(ClientInitGuard)
    }

    fn options(key: &str, host: &str) -> Option<ClientOptions> {
        let error_tracking = ErrorTrackingOptionsBuilder::default()
            .capture_panics(true)
            .in_app_include_paths(vec!["saferskills::".into(), "src/".into()])
            .build()
            .ok()?;
        ClientOptionsBuilder::default()
            .api_key(key.to_string())
            .host(host)
            .request_timeout_seconds(1)
            .shutdown_timeout_ms(1500)
            .max_queue_size(16)
            .max_batch_size(16)
            .disable_geoip(true)
            .is_server(false)
            .error_tracking(error_tracking)
            .before_send(|event| {
                let mut event = super::scrub::scrub_event(event)?;
                event.insert_prop("product", "saferskills").ok()?;
                event.insert_prop("service", "saferskills-cli").ok()?;
                event
                    .insert_prop(
                        "environment",
                        if cfg!(debug_assertions) {
                            "development"
                        } else {
                            "production"
                        },
                    )
                    .ok()?;
                event
                    .insert_prop("release", env!("SAFERSKILLS_RELEASE"))
                    .ok()?;
                event
                    .insert_prop("$exception_release", env!("SAFERSKILLS_RELEASE"))
                    .ok()?;
                event
                    .insert_prop("cli_version", env!("CARGO_PKG_VERSION"))
                    .ok()?;
                if let Some((command, subcommand)) = COMMAND.get() {
                    event.insert_prop("command", command).ok()?;
                    if let Some(subcommand) = subcommand {
                        event.insert_prop("subcommand", subcommand).ok()?;
                    }
                }
                Some(event)
            })
            .build()
            .ok()
    }

    /// Grammar labels only; never argument values. Written once, lock-free reads
    /// from the transport worker cannot deadlock a panicking command.
    pub fn enrich_cli_scope(command: &str, subcommand: Option<&str>) {
        let _ = COMMAND.set((command.to_owned(), subcommand.map(str::to_owned)));
    }

    /// A blocking SDK flush can wait behind transport work. Bound our caller's
    /// wait independently so normal exit and Ctrl-C remain responsive offline.
    pub fn flush(timeout: Duration) {
        if !ACTIVE.load(Ordering::Acquire) {
            return;
        }
        let (tx, rx) = mpsc::sync_channel(1);
        if std::thread::Builder::new()
            .name("crash-flush".into())
            .spawn(move || {
                posthog_rs::flush();
                let _ = tx.send(());
            })
            .is_ok()
        {
            let _ = rx.recv_timeout(timeout);
        }
    }
    #[cfg(test)]
    mod tests {
        use super::*;
        #[test]
        fn panic_child() {
            let Ok(host) = std::env::var("SAFERSKILLS_TEST_CRASH_HOST") else {
                return;
            };
            posthog_rs::init_global(options("phc_test", &host).unwrap()).unwrap();
            if std::env::var_os("SAFERSKILLS_TEST_CRASH_FLUSH").is_some() {
                ACTIVE.store(true, Ordering::Release);
                posthog_rs::capture_exception(&std::io::Error::other("private-token")).unwrap();
                let started = std::time::Instant::now();
                flush(Duration::from_millis(50));
                assert!(started.elapsed() < Duration::from_secs(1));
                return;
            }
            enrich_cli_scope("capability", Some("scan"));
            panic!("private-user-token https://private.invalid /home/private/input.md");
        }

        #[test]
        fn explicit_exit_flush_respects_its_deadline() {
            let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
            let output = std::process::Command::new(std::env::current_exe().unwrap())
                .args(["--exact", "core::crash_report::imp::tests::panic_child"])
                .env(
                    "SAFERSKILLS_TEST_CRASH_HOST",
                    format!("http://{}", listener.local_addr().unwrap()),
                )
                .env("SAFERSKILLS_TEST_CRASH_FLUSH", "1")
                .output()
                .unwrap();
            assert!(
                output.status.success(),
                "{}",
                String::from_utf8_lossy(&output.stderr)
            );
        }

        #[test]
        fn unresponsive_collector_cannot_hold_up_a_panic() {
            let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
            let started = std::time::Instant::now();
            let output = std::process::Command::new(std::env::current_exe().unwrap())
                .args(["--exact", "core::crash_report::imp::tests::panic_child"])
                .env(
                    "SAFERSKILLS_TEST_CRASH_HOST",
                    format!("http://{}", listener.local_addr().unwrap()),
                )
                .output()
                .unwrap();
            assert!(!output.status.success());
            assert!(started.elapsed() < Duration::from_secs(8));
        }

        #[test]
        fn real_panic_is_delivered_once_and_scrubbed() {
            let mut server = mockito::Server::new();
            let expected = server
                .mock("POST", "/batch/")
                .match_request(|request| {
                    let Ok(bytes) = request.body() else {
                        return false;
                    };
                    let Ok(payload) = serde_json::from_slice::<serde_json::Value>(bytes) else {
                        return false;
                    };
                    let serialized = payload.to_string();
                    let props = &payload["batch"][0]["properties"];
                    !serialized.contains("private-user-token")
                        && !serialized.contains("private.invalid")
                        && !serialized.contains("/home/private")
                        && props["service"] == "saferskills-cli"
                        && props["command"] == "capability"
                        && props["$exception_panic_file"]
                            .as_str()
                            .is_some_and(|file| file.starts_with("src/"))
                        && props["$process_person_profile"] == false
                        && props["$exception_list"][0]["type"] == "RustPanic"
                        && props["$exception_list"][0]["stacktrace"]["frames"]
                            .as_array()
                            .is_some_and(|frames| !frames.is_empty())
                })
                .expect(1)
                .with_status(200)
                .with_body("{\"status\":1}")
                .create();
            let output = std::process::Command::new(std::env::current_exe().unwrap())
                .args([
                    "--exact",
                    "core::crash_report::imp::tests::panic_child",
                    "--nocapture",
                ])
                .env("SAFERSKILLS_TEST_CRASH_HOST", server.url())
                .output()
                .unwrap();
            assert!(!output.status.success());
            expected.assert();
        }
    }
}

#[cfg(feature = "crash-report")]
pub use imp::{enrich_cli_scope, flush, init, ClientInitGuard};

#[cfg(not(feature = "crash-report"))]
mod shim {
    pub struct ClientInitGuard;
    pub fn init() -> Option<ClientInitGuard> {
        None
    }
    pub fn enrich_cli_scope(_command: &str, _subcommand: Option<&str>) {}
    pub fn flush(_timeout: std::time::Duration) {}
}
#[cfg(not(feature = "crash-report"))]
pub use shim::{enrich_cli_scope, flush, init, ClientInitGuard};
