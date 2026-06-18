//! Integration tests for the install engine.
//!
//! Detection can't be faked cross-platform (`dirs::home_dir()` reads the OS API,
//! not `$HOME`, on Windows), so these drive the public writer API directly with
//! tempdir paths — deterministic, no network, no real agent. They prove the
//! headline acceptance: **each of the 8 writers round-trips** (install → verify
//! under the correct per-agent key → uninstall restores), comments preserved.
//!
//! NB: this file is NOT named `install_test.rs` — Windows' UAC installer-detection
//! heuristic force-elevates any test binary whose name contains "install"/"setup"
//! /"update", which makes `cargo test` fail to launch it (os error 740).

use saferskills::agents::writer::{ResolvedItem, VerifyStatus};
use saferskills::agents::{writers, AgentId, DetectedAgent, Scope, ALL_AGENTS};

fn mcp_item() -> ResolvedItem {
    ResolvedItem {
        slug: "acme--repo--mcp-server-github".into(),
        name: "github".into(),
        kind: "mcp_server".into(),
        mcp_entry: Some(serde_json::json!({"command":"npx","args":["-y","acme/repo"],"env":{}})),
        ..Default::default()
    }
}

/// Build a DetectedAgent pointing at tempdir paths for `id`. All capability
/// surfaces are wired to the tempdir so the per-kind round-trips can target them.
fn agent_at(id: AgentId, root: &std::path::Path) -> DetectedAgent {
    let config = if id == AgentId::Codex {
        root.join("config.toml")
    } else if id == AgentId::Copilot {
        // CLI surface → mcpServers (the VS Code surface is exercised separately).
        root.join("mcp-config.json")
    } else {
        root.join("mcp.json")
    };
    DetectedAgent {
        id,
        version: None,
        mcp_config_path: config,
        skill_dir: Some(root.join("skills")),
        rules_dir: Some(root.join("rules")),
        hooks_path: Some(root.join("settings.json")),
        plugin_dir: Some(root.join("plugins")),
        scope: Scope::Global,
    }
}

/// The raw config key marker each agent must write under.
fn expected_marker(id: AgentId) -> &'static str {
    match id {
        AgentId::Codex => "[mcp_servers.github]",
        // CLI Copilot + everyone else use the `mcpServers` key.
        _ => "\"github\"",
    }
}

#[test]
fn all_eight_writers_round_trip() {
    for id in ALL_AGENTS {
        let dir = tempfile::tempdir().unwrap();
        let agent = agent_at(id, dir.path());
        let writer = writers::writer_for(id);
        let item = mcp_item();

        // install → the entry lands under the correct per-agent key.
        let changes = writer
            .install(&item, &agent, false)
            .unwrap_or_else(|e| panic!("{id} install failed: {}", e.message));
        assert!(!changes.is_empty(), "{id}: no changes recorded");
        assert_eq!(
            writer.verify(&item, &agent),
            VerifyStatus::Ok,
            "{id}: verify after install"
        );

        let raw = std::fs::read_to_string(&agent.mcp_config_path).unwrap();
        assert!(
            raw.contains(expected_marker(id)),
            "{id}: expected marker {} in:\n{raw}",
            expected_marker(id)
        );

        // uninstall → entry gone again.
        writer.uninstall(&changes).unwrap();
        assert_eq!(
            writer.verify(&item, &agent),
            VerifyStatus::Missing,
            "{id}: verify after uninstall"
        );
    }
}

#[test]
fn copilot_vscode_surface_uses_servers_key() {
    let dir = tempfile::tempdir().unwrap();
    let vscode = dir.path().join(".vscode");
    std::fs::create_dir_all(&vscode).unwrap();
    let agent = DetectedAgent {
        id: AgentId::Copilot,
        version: None,
        mcp_config_path: vscode.join("mcp.json"),
        skill_dir: None,
        rules_dir: None,
        hooks_path: None,
        plugin_dir: None,
        scope: Scope::Project,
    };
    let writer = writers::writer_for(AgentId::Copilot);
    let item = mcp_item();
    let changes = writer.install(&item, &agent, false).unwrap();

    let raw = std::fs::read_to_string(&agent.mcp_config_path).unwrap();
    assert!(
        raw.contains("\"servers\""),
        "VS Code Copilot must use `servers`:\n{raw}"
    );
    assert!(
        !raw.contains("mcpServers"),
        "VS Code Copilot must NOT use mcpServers"
    );
    writer.uninstall(&changes).unwrap();
}

#[test]
fn windsurf_rejects_project_scope() {
    let dir = tempfile::tempdir().unwrap();
    let mut agent = agent_at(AgentId::Windsurf, dir.path());
    agent.scope = Scope::Project;
    let err = writers::writer_for(AgentId::Windsurf)
        .install(&mcp_item(), &agent, false)
        .unwrap_err();
    assert!(err.message.contains("global-only"), "got: {}", err.message);
}

#[test]
fn skill_round_trip_for_claude() {
    let dir = tempfile::tempdir().unwrap();
    let agent = agent_at(AgentId::ClaudeCode, dir.path());
    let writer = writers::writer_for(AgentId::ClaudeCode);

    // Claude Code receives the verbatim SKILL.md text rendered to a single file
    // at <skill_dir>/saferskills/SKILL.md (plan 02) — NOT nested under the slug.
    let skill_md = "---\nname: github\ndescription: x\n---\n\n<!-- pointer:start -->\nscan first\n<!-- pointer:end -->\n";
    let item = ResolvedItem {
        slug: "acme--kit--skill-github".into(),
        name: "github".into(),
        kind: "skill".into(),
        skill_md: Some(skill_md.into()),
        ..Default::default()
    };
    let changes = writer.install(&item, &agent, false).unwrap();
    assert_eq!(writer.verify(&item, &agent), VerifyStatus::Ok);
    let dest = agent
        .skill_dir
        .as_ref()
        .unwrap()
        .join("saferskills")
        .join("SKILL.md");
    assert!(dest.exists(), "verbatim SKILL.md written to saferskills/");
    assert_eq!(std::fs::read_to_string(&dest).unwrap(), skill_md);
    writer.uninstall(&changes).unwrap();
    assert_eq!(writer.verify(&item, &agent), VerifyStatus::Missing);
}

/// A skill is now installable for the rules + AGENTS.md agents too (plan 02): the
/// renderer deposits a `.mdc` / rules `.md` / marker block. Round-trips each.
#[test]
fn skill_round_trip_for_rules_and_agents_md_agents() {
    let skill_md = "---\nname: saferskills\ndescription: scan it\n---\n\n<!-- pointer:start -->\nscan before you trust\n<!-- pointer:end -->\n\n## Core workflow\nbody only\n";
    let item = ResolvedItem {
        slug: "acme--kit--skill-saferskills".into(),
        name: "saferskills".into(),
        kind: "skill".into(),
        skill_md: Some(skill_md.into()),
        ..Default::default()
    };

    // Cursor → .mdc rule (File).
    {
        let dir = tempfile::tempdir().unwrap();
        let agent = agent_at(AgentId::Cursor, dir.path());
        let writer = writers::writer_for(AgentId::Cursor);
        let changes = writer.install(&item, &agent, false).unwrap();
        let mdc = agent.rules_dir.as_ref().unwrap().join("saferskills.mdc");
        assert!(mdc.exists(), "cursor .mdc written");
        let body = std::fs::read_to_string(&mdc).unwrap();
        assert!(body.contains("alwaysApply: false"), "mdc frontmatter");
        assert!(body.contains("## Core workflow"), "full body in .mdc");
        assert_eq!(writer.verify(&item, &agent), VerifyStatus::Ok);
        writer.uninstall(&changes).unwrap();
        assert!(!mdc.exists(), "uninstall removes the .mdc");
    }

    // Codex → marker block in AGENTS.md (Block). Global scope → skill_dir parent.
    {
        let dir = tempfile::tempdir().unwrap();
        let agent = agent_at(AgentId::Codex, dir.path());
        let writer = writers::writer_for(AgentId::Codex);
        let host = dir.path().join("AGENTS.md");
        std::fs::write(&host, "# Repo guide\n").unwrap();
        let changes = writer.install(&item, &agent, false).unwrap();
        let after = std::fs::read_to_string(&host).unwrap();
        assert!(after.contains("# Repo guide"), "host content preserved");
        assert!(after.contains("## SaferSkills"), "marker block merged");
        assert_eq!(writer.verify(&item, &agent), VerifyStatus::Ok);
        writer.uninstall(&changes).unwrap();
        let restored = std::fs::read_to_string(&host).unwrap();
        assert_eq!(
            restored.trim(),
            "# Repo guide",
            "block stripped, host intact"
        );
    }
}

/// Installing a skill to Codex then Copilot into ONE shared `AGENTS.md` writes the
/// block once — the second install is a no-op replace (shared-host idempotency,
/// plan 02). Uses two global-scope agents pointed at the same host dir so the test
/// never mutates the process-global cwd (parallel-safe).
#[test]
fn codex_then_copilot_share_one_agents_md() {
    use saferskills::agents::writers::render::MARKER_START;

    let shared = tempfile::tempdir().unwrap();
    let skill_md = "---\nname: saferskills\ndescription: scan it\n---\n\n<!-- pointer:start -->\nscan first\n<!-- pointer:end -->\n";
    let item = ResolvedItem {
        slug: "acme--kit--skill-saferskills".into(),
        name: "saferskills".into(),
        kind: "skill".into(),
        skill_md: Some(skill_md.into()),
        ..Default::default()
    };

    // Both global agents resolve AGENTS.md to `<skill_dir parent>/AGENTS.md` — point
    // both skill_dirs at the SAME parent so they target one shared host file.
    let mut codex = agent_at(AgentId::Codex, shared.path());
    codex.skill_dir = Some(shared.path().join("skills"));
    let mut copilot = agent_at(AgentId::Copilot, shared.path());
    copilot.skill_dir = Some(shared.path().join("skills"));

    writers::writer_for(AgentId::Codex)
        .install(&item, &codex, false)
        .unwrap();
    writers::writer_for(AgentId::Copilot)
        .install(&item, &copilot, false)
        .unwrap();

    let host = shared.path().join("AGENTS.md");
    let body = std::fs::read_to_string(&host).unwrap();
    assert_eq!(
        body.matches(MARKER_START).count(),
        1,
        "exactly one SaferSkills block in the shared AGENTS.md:\n{body}"
    );
}

#[test]
fn claude_fixture_preserves_comment_and_restores_byte_for_byte() {
    let before = include_str!("fixtures/claude_code/before.jsonc");
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("mcp.json");
    std::fs::write(&path, before).unwrap();

    let agent = DetectedAgent {
        id: AgentId::ClaudeCode,
        version: None,
        mcp_config_path: path.clone(),
        skill_dir: None,
        rules_dir: None,
        hooks_path: None,
        plugin_dir: None,
        scope: Scope::Global,
    };
    let writer = writers::writer_for(AgentId::ClaudeCode);
    let item = mcp_item();
    let changes = writer.install(&item, &agent, false).unwrap();

    let after = std::fs::read_to_string(&path).unwrap();
    assert!(after.contains("user's own comment"), "comment preserved");
    assert!(
        after.contains("existing-server"),
        "sibling server preserved"
    );
    assert!(after.contains("\"github\""), "new server added");

    writer.uninstall(&changes).unwrap();
    assert_eq!(
        std::fs::read_to_string(&path).unwrap(),
        before,
        "byte-for-byte restore"
    );
}

#[test]
fn codex_fixture_preserves_comment_and_restores() {
    let before = include_str!("fixtures/codex/before.toml");
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("config.toml");
    std::fs::write(&path, before).unwrap();

    let agent = DetectedAgent {
        id: AgentId::Codex,
        version: None,
        mcp_config_path: path.clone(),
        skill_dir: None,
        rules_dir: None,
        hooks_path: None,
        plugin_dir: None,
        scope: Scope::Global,
    };
    let writer = writers::writer_for(AgentId::Codex);
    let item = mcp_item();
    let changes = writer.install(&item, &agent, false).unwrap();

    let after = std::fs::read_to_string(&path).unwrap();
    assert!(
        after.contains("the user's own comment"),
        "comment preserved"
    );
    assert!(after.contains("model = \"o3\""), "setting preserved");
    assert!(
        after.contains("[mcp_servers.github]"),
        "new server table added"
    );

    writer.uninstall(&changes).unwrap();
    assert_eq!(
        std::fs::read_to_string(&path).unwrap(),
        before,
        "byte-for-byte restore"
    );
}

#[test]
fn openclaw_probes_existing_nested_key_shape() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("openclaw.json");
    std::fs::write(&path, "{\n  \"mcp\": { \"servers\": {} }\n}\n").unwrap();
    let agent = DetectedAgent {
        id: AgentId::Openclaw,
        version: None,
        mcp_config_path: path.clone(),
        skill_dir: None,
        rules_dir: None,
        hooks_path: None,
        plugin_dir: None,
        scope: Scope::Global,
    };
    let writer = writers::writer_for(AgentId::Openclaw);
    let item = mcp_item();
    let changes = writer.install(&item, &agent, false).unwrap();
    let raw = std::fs::read_to_string(&path).unwrap();
    // Respected the existing nested shape rather than adding a top-level key.
    assert!(raw.contains("\"servers\""));
    assert!(writer.verify(&item, &agent) == VerifyStatus::Ok);
    writer.uninstall(&changes).unwrap();
}

// ── rules / hook / plugin install shapes (every-kind expansion) ──────────────

#[test]
fn rules_round_trip_for_each_compatible_agent() {
    // rules → cursor / windsurf / cline / copilot, each with its own extension.
    for (id, ext) in [
        (AgentId::Cursor, ".mdc"),
        (AgentId::Windsurf, ".md"),
        (AgentId::Cline, ".md"),
        (AgentId::Copilot, ".instructions.md"),
    ] {
        let dir = tempfile::tempdir().unwrap();
        let agent = agent_at(id, dir.path());
        let writer = writers::writer_for(id);
        let item = ResolvedItem {
            slug: "acme--repo--rules-style".into(),
            name: "style".into(),
            kind: "rules".into(),
            rules_body: Some(b"# Be consistent".to_vec()),
            ..Default::default()
        };
        let changes = writer
            .install(&item, &agent, false)
            .unwrap_or_else(|e| panic!("{id} rules install: {}", e.message));
        assert_eq!(
            writer.verify(&item, &agent),
            VerifyStatus::Ok,
            "{id}: verify"
        );
        let expected = agent
            .rules_dir
            .as_ref()
            .unwrap()
            .join(format!("style{ext}"));
        assert!(expected.exists(), "{id}: expected {}", expected.display());
        writer.uninstall(&changes).unwrap();
        assert_eq!(
            writer.verify(&item, &agent),
            VerifyStatus::Missing,
            "{id}: after uninstall"
        );
    }
}

#[test]
fn hook_round_trip_and_byte_for_byte_restore() {
    let dir = tempfile::tempdir().unwrap();
    let settings = dir.path().join("settings.json");
    // A pre-existing hooks block + a sibling comment that must survive.
    let before = "{\n  // user's own comment\n  \"hooks\": {\n    \"PreToolUse\": []\n  }\n}\n";
    std::fs::write(&settings, before).unwrap();
    let agent = DetectedAgent {
        id: AgentId::ClaudeCode,
        version: None,
        mcp_config_path: dir.path().join("mcp.json"),
        skill_dir: None,
        rules_dir: None,
        hooks_path: Some(settings.clone()),
        plugin_dir: None,
        scope: Scope::Global,
    };
    let item = ResolvedItem {
        slug: "acme--repo--hook-guard".into(),
        name: "guard".into(),
        kind: "hook".into(),
        hook_entry: Some(serde_json::json!({
            "PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo hi"}]}]
        })),
        ..Default::default()
    };
    let writer = writers::writer_for(AgentId::ClaudeCode);
    let changes = writer.install(&item, &agent, false).unwrap();
    let after = std::fs::read_to_string(&settings).unwrap();
    assert!(
        after.contains("user's own comment"),
        "comment preserved:\n{after}"
    );
    assert!(after.contains("PostToolUse"), "new event merged:\n{after}");
    assert_eq!(writer.verify(&item, &agent), VerifyStatus::Ok);

    writer.uninstall(&changes).unwrap();
    assert_eq!(
        std::fs::read_to_string(&settings).unwrap(),
        before,
        "byte-for-byte restore"
    );
    assert_eq!(writer.verify(&item, &agent), VerifyStatus::Missing);
}

#[test]
fn plugin_install_lands_and_enumerate_rediscovers() {
    use saferskills::agents::enumerate::{enumerate_from, CapKind};

    let dir = tempfile::tempdir().unwrap();
    let plugins_root = dir.path().join("plugins");

    // A minimal plugin bundle zip — the `.claude-plugin/plugin.json` anchor.
    let mut buf = Vec::new();
    {
        use std::io::Write as _;
        let mut w = zip::ZipWriter::new(std::io::Cursor::new(&mut buf));
        let opts: zip::write::FileOptions<'_, ()> = zip::write::FileOptions::default();
        w.start_file(".claude-plugin/plugin.json", opts).unwrap();
        w.write_all(br#"{"name":"ksail","version":"0.1.0"}"#)
            .unwrap();
        w.finish().unwrap();
    }

    let agent = DetectedAgent {
        id: AgentId::ClaudeCode,
        version: None,
        mcp_config_path: dir.path().join("mcp.json"),
        skill_dir: None,
        rules_dir: None,
        hooks_path: None,
        plugin_dir: Some(plugins_root.clone()),
        scope: Scope::Global,
    };
    let item = ResolvedItem {
        slug: "devantler-tech--ksail--plugin-ksail".into(),
        name: "ksail".into(),
        kind: "plugin".into(),
        plugin_zip: Some(buf),
        component_path: Some(String::new()),
        plugin_marketplace: Some("devantler-tech-ksail".into()),
        plugin_version: Some("0.1.0".into()),
        ..Default::default()
    };
    let writer = writers::writer_for(AgentId::ClaudeCode);
    let changes = writer.install(&item, &agent, false).unwrap();
    assert_eq!(changes.len(), 2, "version dir + ledger entry");

    let vdir = plugins_root
        .join("cache")
        .join("devantler-tech-ksail")
        .join("ksail")
        .join("0.1.0");
    assert!(
        vdir.join(".claude-plugin").join("plugin.json").exists(),
        "version dir populated"
    );
    let ledger = std::fs::read_to_string(plugins_root.join("installed_plugins.json")).unwrap();
    assert!(
        ledger.contains("ksail@devantler-tech-ksail"),
        "ledger entry: {ledger}"
    );
    assert_eq!(writer.verify(&item, &agent), VerifyStatus::Ok);

    // Close the read/write loop: the local-audit enumerator re-discovers it.
    // (enumerate derives the Claude root from skill_dir.parent(), so give one.)
    let enum_agent = DetectedAgent {
        id: AgentId::ClaudeCode,
        version: None,
        mcp_config_path: dir.path().join("mcp.json"),
        skill_dir: Some(dir.path().join("skills")),
        rules_dir: None,
        hooks_path: None,
        plugin_dir: Some(plugins_root.clone()),
        scope: Scope::Global,
    };
    let found = enumerate_from(&[enum_agent]);
    assert!(
        found
            .capabilities
            .iter()
            .any(|c| c.kind == CapKind::Plugin && c.name == "ksail"),
        "enumerate should re-discover the installed plugin"
    );

    writer.uninstall(&changes).unwrap();
    assert!(!vdir.exists(), "version dir removed on uninstall");
    assert_eq!(writer.verify(&item, &agent), VerifyStatus::Missing);
}
