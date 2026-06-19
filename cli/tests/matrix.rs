//! The synthetic 8-agent install matrix (CLI-12, the DoD coverage gate).
//!
//! For **every** one of the 8 agents this drives `install → uninstall` through
//! the real binary against a mock catalog API, with a **faked** install surface
//! for that agent under a throw-away `HOME`. It asserts the MCP server entry
//! lands under the agent's **correct key landmine** (`mcpServers` vs the VS-Code
//! `servers` vs Codex TOML `[mcp_servers.x]` vs OpenClaw's nested `mcp.servers`)
//! and that `uninstall` reverses it cleanly. Skill-capable agents additionally
//! get a `SKILL.md` folder-copy + removal pass.
//!
//! This is the **8× (agent) dimension** of the 8×3 matrix; the **×3 (OS)**
//! dimension is the existing `publish-npm.yml` 5-target build + the 3-OS
//! `verify-publish` smoke (the openlatch-client approach — cross-OS lives in the
//! release matrix, not a per-PR lane), plus the manual `matrix/RUNBOOK.md`
//! real-agent sign-off. See that runbook for the full ×3 contract.
//!
//! **Unix-only.** `dirs::home_dir()` honours `$HOME` only on unix, so a temp-HOME
//! fake surface is detected there; on Windows it reads the OS API. The coverage
//! lane runs on Linux, so this is where the per-agent matrix coverage comes from
//! (mirrors `lifecycle_cli.rs`).
#![cfg(unix)]

use std::fs;
use std::io::{Cursor, Write as _};
use std::path::Path;

use assert_cmd::Command;
use mockito::{Matcher, Server, ServerGuard};
use serde_json::Value;
use tempfile::TempDir;

/// `capability_name(slug, kind)` strips the `<kind>-` prefix, so both slugs below
/// resolve to the server/folder name `demo` (the MCP key + the skill folder).
const MCP_SLUG: &str = "acme--repo--mcp-server-demo";
const SKILL_SLUG: &str = "acme--repo--skill-demo";
const NAME: &str = "demo";
const ALL_AGENTS: &str =
    r#"["claude-code","cursor","codex","copilot","windsurf","cline","gemini","openclaw"]"#;

/// Where + under which key an agent's MCP entry must land (global scope, unix).
enum Key {
    /// JSON config; the entry sits under this nested key path → `<name>`.
    Json(&'static [&'static str]),
    /// Codex TOML config; the entry is the `[mcp_servers.<name>]` table.
    Toml,
}

struct Case {
    id: &'static str,
    /// MCP config file, relative to `$HOME`.
    config: &'static str,
    key: Key,
    /// Skill dir relative to `$HOME`, or `None` for the MCP-only agents.
    skill_dir: Option<&'static str>,
}

/// The 8 agents — detection signal, MCP config path, key landmine, skill support.
/// Derived from the agent-config schemas + `cli/src/agents/{detect,writers}`.
const CASES: &[Case] = &[
    Case {
        id: "claude-code",
        config: ".claude.json",
        key: Key::Json(&["mcpServers"]),
        skill_dir: Some(".claude/skills"),
    },
    Case {
        id: "cursor",
        config: ".cursor/mcp.json",
        key: Key::Json(&["mcpServers"]),
        skill_dir: None,
    },
    Case {
        id: "codex",
        config: ".codex/config.toml",
        key: Key::Toml,
        skill_dir: Some(".codex/skills"),
    },
    Case {
        id: "copilot",
        config: ".copilot/mcp-config.json",
        key: Key::Json(&["mcpServers"]),
        skill_dir: Some(".copilot/skills"),
    },
    Case {
        id: "windsurf",
        config: ".codeium/windsurf/mcp_config.json",
        key: Key::Json(&["mcpServers"]),
        skill_dir: None,
    },
    Case {
        id: "cline",
        config: ".cline/mcp.json",
        key: Key::Json(&["mcpServers"]),
        skill_dir: None,
    },
    Case {
        id: "gemini",
        config: ".gemini/settings.json",
        key: Key::Json(&["mcpServers"]),
        skill_dir: Some(".gemini/skills"),
    },
    Case {
        id: "openclaw",
        config: ".openclaw/openclaw.json",
        key: Key::Json(&["mcpServers"]),
        skill_dir: Some(".openclaw/skills"),
    },
];

// ─── fixtures ────────────────────────────────────────────────────────────────

/// Materialize the **minimal** filesystem signal that makes `detect` see this
/// agent — never a binary on PATH, so the matrix stays hermetic.
fn materialize(home: &Path, id: &str) {
    match id {
        // A file signal (or `~/.claude` dir) — `.claude.json` is both.
        "claude-code" => fs::write(home.join(".claude.json"), b"{}\n").unwrap(),
        "cursor" => fs::create_dir_all(home.join(".cursor")).unwrap(),
        "codex" => fs::create_dir_all(home.join(".codex")).unwrap(),
        "copilot" => fs::create_dir_all(home.join(".copilot")).unwrap(),
        "windsurf" => fs::create_dir_all(home.join(".codeium/windsurf")).unwrap(),
        "cline" => fs::create_dir_all(home.join(".cline")).unwrap(),
        "gemini" => fs::create_dir_all(home.join(".gemini")).unwrap(),
        "openclaw" => fs::create_dir_all(home.join(".openclaw")).unwrap(),
        other => panic!("unknown agent {other}"),
    }
}

fn item_json(slug: &str, kind: &str) -> String {
    format!(
        r#"{{
          "id": "id-1",
          "slug": "{slug}",
          "kind": "{kind}",
          "display_name": "{NAME}",
          "github_org": "acme",
          "github_repo": "repo",
          "popularity_tier": "emerging",
          "popularity_score": 10,
          "latest_scan_score": 92,
          "latest_scan_tier": "green",
          "findings_count": 0,
          "registries": [],
          "agent_compatibility": {ALL_AGENTS},
          "updated_at": "2026-06-01T00:00:00Z"
        }}"#
    )
}

fn detail_json(slug: &str, kind: &str) -> String {
    format!(
        r#"{{
          "item": {item},
          "latest_scan": {{
            "id": "scan-1", "slug": "{slug}", "display_name": "{NAME}",
            "aggregate_score": 92, "tier": "green", "sub_scores": {{}},
            "score_breakdown": {{}}, "findings": [],
            "scanned_at": "2026-06-01T00:00:00Z", "rubric_version": "abc1234",
            "engine_version": "1.0", "latency_ms": 12, "source": "github",
            "status": "completed"
          }}
        }}"#,
        item = item_json(slug, kind)
    )
}

/// A `SKILL.md`-bearing `.zip` the skill download endpoint serves. Carries a
/// `<!-- pointer:start/end -->` block — the always-on form the renderer lifts for
/// the rules-/AGENTS.md agents (Cline, Windsurf, Codex, Copilot, Gemini); a skill
/// without one can't render to those surfaces.
fn skill_zip() -> Vec<u8> {
    let mut buf = Vec::new();
    {
        let mut w = zip::ZipWriter::new(Cursor::new(&mut buf));
        let opts: zip::write::FileOptions<'_, ()> = zip::write::FileOptions::default();
        w.start_file("SKILL.md", opts).unwrap();
        w.write_all(
            b"---\nname: demo\n---\n# Demo\n\n<!-- pointer:start -->\nScan before you trust.\n<!-- pointer:end -->\n",
        )
        .unwrap();
        w.finish().unwrap();
    }
    buf
}

/// A mock catalog API serving one item (`kind`) + its detail + health, and — for
/// a skill — its download `.zip`. Reused across every agent in the loop.
fn mock_api(slug: &str, kind: &str) -> ServerGuard {
    let mut server = Server::new();
    server
        .mock("GET", "/api/v1/items")
        .match_query(Matcher::Any)
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(format!(
            r#"{{ "data": [{item}], "total_count": 1, "page": 1, "total_pages": 1, "page_size": 24 }}"#,
            item = item_json(slug, kind)
        ))
        .expect_at_least(1)
        .create();
    server
        .mock("GET", format!("/api/v1/items/{slug}").as_str())
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(detail_json(slug, kind))
        .expect_at_least(1)
        .create();
    if kind == "skill" {
        server
            .mock("GET", format!("/api/v1/items/{slug}/download").as_str())
            .with_status(200)
            .with_header("content-type", "application/zip")
            .with_body(skill_zip())
            .expect_at_least(1)
            .create();
    }
    server
        .mock("GET", "/api/v1/health")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{ "status": "ok", "version": "1.0", "git_sha": "abc", "migrations_ok": true }"#,
        )
        .create();
    server
}

/// A `saferskills` command isolated from the host: throw-away `SAFERSKILLS_DIR`,
/// a faked `HOME` carrying one agent's surface, a hermetic `XDG_CONFIG_HOME`
/// (pins Cline's VS-Code-globalStorage probe inside the fake home), and the mock
/// API. `CI=1` keeps telemetry + the first-run audit/consent prompts off.
fn cli(ss: &Path, home: &Path, api: &str) -> Command {
    let mut cmd = Command::cargo_bin("saferskills").unwrap();
    cmd.env("SAFERSKILLS_DIR", ss)
        .env("HOME", home)
        .env("XDG_CONFIG_HOME", home.join(".config"))
        .env("SAFERSKILLS_API_URL", api)
        .env("CI", "1")
        .env("NO_COLOR", "1");
    cmd
}

// ─── assertions ──────────────────────────────────────────────────────────────

fn json_has(path: &Path, key: &[&str], name: &str) -> bool {
    let Ok(text) = fs::read_to_string(path) else {
        return false;
    };
    let Ok(root) = serde_json::from_str::<Value>(&text) else {
        return false;
    };
    let mut cur = &root;
    for seg in key {
        match cur.get(seg) {
            Some(next) => cur = next,
            None => return false,
        }
    }
    cur.get(name).is_some()
}

fn toml_has(path: &Path, name: &str) -> bool {
    let Ok(text) = fs::read_to_string(path) else {
        return false;
    };
    let Ok(doc) = toml::from_str::<toml::Value>(&text) else {
        return false;
    };
    doc.get("mcp_servers").and_then(|s| s.get(name)).is_some()
}

fn entry_present(case: &Case, config: &Path) -> bool {
    match case.key {
        Key::Json(key) => json_has(config, key, NAME),
        Key::Toml => toml_has(config, NAME),
    }
}

// ─── the matrix ──────────────────────────────────────────────────────────────

/// For every agent: install an MCP server, assert it landed under the correct
/// per-agent key, then uninstall and assert the key is gone.
#[test]
fn mcp_install_lands_under_correct_key_and_reverses_for_every_agent() {
    let server = mock_api(MCP_SLUG, "mcp_server");
    let api = server.url();

    for case in CASES {
        let ss = TempDir::new().unwrap();
        let home = TempDir::new().unwrap();
        materialize(home.path(), case.id);
        let config = home.path().join(case.config);
        let run = || cli(ss.path(), home.path(), &api);

        // install → the MCP entry must land under the agent's correct key.
        run()
            .args(["--json", "install", NAME, "--to", case.id, "--yes"])
            .assert()
            .success();
        assert!(
            entry_present(case, &config),
            "[{}] MCP entry must land under the correct key in {}",
            case.id,
            config.display()
        );

        // uninstall → the entry must be gone (prior was empty → key removed).
        run().args(["--json", "uninstall", NAME]).assert().success();
        assert!(
            !entry_present(case, &config),
            "[{}] uninstall must reverse the MCP entry",
            case.id
        );
    }
}

/// For every skill-capable agent: install a skill and assert it landed in the
/// agent's NATIVE form, then uninstall and assert it is reversed. Verbatim agents
/// (Claude Code / OpenClaw) get `<skill_dir>/<name>/SKILL.md` (name-keyed — D1);
/// the AGENTS.md / GEMINI.md agents (Codex / Copilot / Gemini) get a marker block
/// merged into the shared host file at the agent home (global scope = `skill_dir`
/// parent), NOT the no-op skills dir (D6).
#[test]
fn skill_install_copies_and_reverses_for_supporting_agents() {
    let server = mock_api(SKILL_SLUG, "skill");
    let api = server.url();

    for case in CASES.iter().filter(|c| c.skill_dir.is_some()) {
        let ss = TempDir::new().unwrap();
        let home = TempDir::new().unwrap();
        materialize(home.path(), case.id);
        let run = || cli(ss.path(), home.path(), &api);

        run()
            .args(["--json", "install", NAME, "--to", case.id, "--yes"])
            .assert()
            .success();

        if matches!(case.id, "claude-code" | "openclaw") {
            // Verbatim SKILL.md at <skill_dir>/<name>/SKILL.md (name-keyed, D1).
            let skill = home
                .path()
                .join(case.skill_dir.unwrap())
                .join(NAME)
                .join("SKILL.md");
            assert!(
                skill.exists(),
                "[{}] verbatim SKILL.md must be copied to {}",
                case.id,
                skill.display()
            );
            run().args(["--json", "uninstall", NAME]).assert().success();
            assert!(
                !skill.exists(),
                "[{}] uninstall must remove the skill folder",
                case.id
            );
        } else {
            // Codex / Copilot / Gemini → a marker block merged into the shared
            // AGENTS.md / GEMINI.md at the agent home (skill_dir parent), D6.
            let host_file = if case.id == "gemini" {
                "GEMINI.md"
            } else {
                "AGENTS.md"
            };
            let host = home
                .path()
                .join(Path::new(case.skill_dir.unwrap()).parent().unwrap())
                .join(host_file);
            let installed = fs::read_to_string(&host).unwrap_or_default();
            assert!(
                installed.contains("<!-- saferskills:start -->"),
                "[{}] install must merge the marker block into {}",
                case.id,
                host.display()
            );
            run().args(["--json", "uninstall", NAME]).assert().success();
            let after = fs::read_to_string(&host).unwrap_or_default();
            assert!(
                !after.contains("<!-- saferskills:start -->"),
                "[{}] uninstall must strip the marker block from {}",
                case.id,
                host.display()
            );
        }
    }
}

/// OpenClaw's key shape is ambiguous (`mcpServers` vs nested `mcp.servers`). When
/// the config already uses the nested shape, the writer must respect it — the
/// load-bearing config-schema landmine.
#[test]
fn openclaw_respects_preexisting_nested_mcp_servers_key() {
    let server = mock_api(MCP_SLUG, "mcp_server");
    let api = server.url();

    let ss = TempDir::new().unwrap();
    let home = TempDir::new().unwrap();
    let dir = home.path().join(".openclaw");
    fs::create_dir_all(&dir).unwrap();
    let config = dir.join("openclaw.json");
    fs::write(&config, br#"{ "mcp": { "servers": {} } }"#).unwrap();
    let run = || cli(ss.path(), home.path(), &api);

    run()
        .args(["--json", "install", NAME, "--to", "openclaw", "--yes"])
        .assert()
        .success();
    assert!(
        json_has(&config, &["mcp", "servers"], NAME),
        "openclaw must write under the pre-existing nested mcp.servers key"
    );
    assert!(
        !json_has(&config, &["mcpServers"], NAME),
        "openclaw must NOT create a parallel top-level mcpServers key"
    );

    run().args(["--json", "uninstall", NAME]).assert().success();
    assert!(
        !json_has(&config, &["mcp", "servers"], NAME),
        "uninstall must reverse the nested entry"
    );
}
