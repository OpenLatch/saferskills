# Agent config schemas + live-verification checklist (D-05-15)

Pinned known-good config shapes the 8 writers target, with the official source +
retrieval date. The MEDIUM/LOW (volatile) surfaces carry a **live-verification
gate**: their checkbox stays ☐ until a maintainer installs the entry against a
real running agent and confirms it loads, then ticks it here. A surface that
cannot be verified ships **detect-only with a copy-paste fallback** for that one
surface — never a per-agent descope (the full-8 wedge is non-negotiable).

> This CLI installs **every capability kind** the platform catalogs across every
> compatible agent (the original two-shape scope of D-05-16 was widened): the five
> install shapes are `mcp_server` (format-preserving map-merge), `skill` (folder
> copy), `rules` (single-file copy), `hook` (per-event `settings.json` merge), and
> `plugin` (native bundle install). The per-capability config the CLI needs comes
> from the backend `install_spec` field (`app/scan/discovery.py::build_install_spec`)
> on the report — not CLI-side zip re-parsing. The backend `agent_compatibility` is
> the outer filter, so a writer never sees a kind its agent can't take; the on-disk
> surface check is `writer::kind_supported`.

## MCP map-merge — per-agent key + URL landmines

| Agent | Conf. | Config file (global / project) | MCP key | URL field | Source (2026-06-04) |
|---|---|---|---|---|---|
| claude-code | HIGH | `~/.claude.json` / `.mcp.json` | `mcpServers` | `url` | code.claude.com/docs/en/mcp |
| cursor | HIGH | `~/.cursor/mcp.json` / `.cursor/mcp.json` | `mcpServers` | `url` | cursor.com/docs/mcp |
| windsurf | HIGH (MCP) | `~/.codeium/windsurf/mcp_config.json` (global only) | `mcpServers` | **`serverUrl`** | docs.windsurf.com/windsurf/cascade/mcp |
| copilot (CLI) | HIGH | `~/.copilot/mcp-config.json` | `mcpServers` | `url` | docs.github.com copilot-cli |
| copilot (VS Code) | HIGH | `.vscode/mcp.json` (project) | **`servers`** | `url` | code.visualstudio.com/docs/agent-customization/mcp-servers |
| codex | HIGH | `~/.codex/config.toml` / `.codex/config.toml` | TOML `[mcp_servers.<n>]` | `url`+`bearer_token_env_var` | developers.openai.com/codex/mcp |
| gemini | HIGH (MCP) | `~/.gemini/settings.json` / `.gemini/settings.json` | `mcpServers` | `url` / `httpUrl` | github.com/google-gemini/gemini-cli docs/tools/mcp-server.md |
| cline | HIGH (MCP) | VS Code globalStorage `…/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` (variant-resolved) / `~/.cline/mcp.json` | `mcpServers` | `url` | docs.cline.bot/mcp/configuring-mcp-servers |
| openclaw | **MED** | `~/.openclaw/openclaw.json` / `.mcp.json` | **`mcpServers` ∨ `mcp.servers` (probed)** | `url` | docs.openclaw.ai/cli/mcp (key-shape unverified) |

Notes:
- **claude-code local-scope nesting** (`projects."<abs>".mcpServers`) is NOT used —
  both our scopes write the top-level `mcpServers` (global → `~/.claude.json`,
  project → `.mcp.json`). This avoids a dotted-key that contains the abs path.
- **Idempotency hazards** (re-verify after write — `doctor`/`verify()` re-reads):
  Codex Desktop has rewritten/dropped MCP entries on a Windows restart; OpenClaw +
  Windsurf need a gateway/editor restart to apply ("write succeeded" ≠ "active").

## Skill folder copy

| Agent | Skills dir | Notes |
|---|---|---|
| claude-code | `~/.claude/skills/<name>/` · `.claude/skills/<name>/` | HIGH |
| openclaw | `~/.openclaw/skills/<name>/` | MED (dir path unverified) |
| codex / copilot / gemini | `~/.codex/skills/` · `~/.copilot/skills/` · `~/.gemini/skills/` | dirs known, but the backend `agent_compatibility` keeps skills off these agents, so the CLI never offers a skill install there |

Frontmatter `name` must equal the folder name (Copilot/VS Code enforces it); the
writer copies the SaferSkills snapshot `.zip` into `<skills>/<name>/`.

## Rules file copy

| Agent | Rules dir (global / project) | File extension | Backend compat |
|---|---|---|---|
| cursor | `~/.cursor/rules` / `.cursor/rules` | `.mdc` | ✓ |
| windsurf | `.windsurf/rules` (workspace) | `.md` | ✓ |
| cline | `~/Documents/Cline/Rules` / `.clinerules` | `.md` | ✓ |
| copilot | `.github/instructions` (repo-level) | `.instructions.md` | ✓ |

`install_rules_file` copies the source rules body (read from the snapshot `.zip` at
`install_spec.rules_files[0].path`) to `<rules_dir>/<name><ext>` → an
[`InstallChange::File`]. Verify = the file exists; uninstall = remove it.

## Hook settings.json merge

| Agent | Settings file (global / project) | Block | Backend compat |
|---|---|---|---|
| claude-code | `~/.claude/settings.json` / `.claude/settings.json` | top-level `hooks` | ✓ |
| openclaw | `~/.openclaw/openclaw.json` (probe-and-adapt) | top-level `hooks` | ✓ (hook only) |

`merge_json_hook` merges the source `hooks` block (the `hooks` value of the
capability's anchor file in the snapshot, or the file itself when its top-level keys
ARE the events) into the settings `hooks` block, recording one `ConfigKey`
`hooks.<event>` per event so uninstall byte-restores via `restore_json_key` (a new
event is removed exactly; an existing event is restored to its prior array).
Claude hooks live in `settings.json`, **not** the MCP config path — hence the
distinct `hooks_path` on `DetectedAgent`.

## Plugin native bundle install

| Agent | Plugins root | Layout | Backend compat |
|---|---|---|---|
| claude-code | `~/.claude/plugins` | `cache/<mp>/<plugin>/<ver>/` + `installed_plugins.json` | ✓ |
| openclaw | — | layout not yet live-verified → gated OFF | ✓ (deferred) |

`install_plugin` extracts the bundle `.zip` (prefix-stripped to `component_path`)
into `<plugins>/cache/<mp>/<plugin>/<ver>/` — the exact layout the local-audit
enumerator (`enumerate.rs::discover_plugins`) reads — and merges a
`plugins["<plugin>@<mp>"].installs[] = {scope:"user", version}` ledger entry into
`installed_plugins.json`. `<plugin>`/`<ver>` come from `install_spec.plugin_ref`
(`<ver>` falls back to `ref_sha[..7]`); `<mp>` is a stable id derived from the repo
coordinates (`<org>-<repo>`) — we own both the write and the read, so it round-trips.
Recorded as a `File` (the version dir) + a `ConfigKey` (the ledger, restoring the
whole prior `plugins` map). NOT a shell-out to `claude` — that would forfeit the
reversible-install guarantee. A `lifecycle_test` closes the loop: install → assert
the version dir + ledger land → `enumerate_from` re-discovers the plugin → uninstall.

### OpenClaw caveat (flagged risk, not a silent drop)

OpenClaw is in the `hook` + `plugin` backend compat set, but its on-disk hook/plugin
layout is **not yet documented** in `enumerate.rs` (the plugin enumerator
early-returns for non-Claude). So:
- **OpenClaw hook** ships against its own config file (`hooks_path = ~/.openclaw/
  openclaw.json`), probe-and-adapt like the MCP key shape — best-effort until
  live-verified.
- **OpenClaw plugin** is gated OFF (`plugin_dir = None` ⇒ `kind_supported` returns
  false) until its layout is live-verified and added to `enumerate.rs` + `detect.rs`.
  The backend `install_spec.plugin_ref` is agent-agnostic, so enabling it later is a
  CLI-only follow-up.

## Live-verification checklist (MED/LOW surfaces)

Tick after a real install loads the entry in the running agent; record the date +
agent version. Until ticked, treat the surface as best-effort.

- [ ] **openclaw — MCP key shape** (`mcpServers` vs `mcp.servers`): confirm the
      probed key matches what a running OpenClaw gateway reads. _(verified by: ___, date: ___, version: ___)_
- [ ] **openclaw — skills dir** (`~/.openclaw/skills/`): confirm a copied skill loads.
- [ ] **cline — globalStorage variant resolution**: confirm the resolved
      `Code` / `Code - Insiders` / `VSCodium` path is the one the running extension reads.
- [ ] **windsurf — MCP apply-on-restart**: confirm the merged `mcp_config.json`
      entry is picked up after a Cascade restart.
- [ ] **rules dest paths** (cursor `.mdc`, windsurf `.md`, cline `Rules/`,
      copilot `.github/instructions/*.instructions.md`): confirm a copied rules file
      is the one each running agent reads.
- [ ] **claude-code — hook apply**: confirm a merged `settings.json` `hooks` block
      fires in a running session.
- [ ] **openclaw — hook config file**: confirm `~/.openclaw/openclaw.json` is where a
      running OpenClaw reads its `hooks` block (the probe-and-adapt target).
- [ ] **openclaw — plugin layout** (currently gated OFF): document + verify before
      flipping `plugin_dir` on in `detect.rs`.

Out-of-scope surfaces (NOT written by this CLI — no live-verify needed here):
Gemini skill dir, Codex `openai.yaml`. (Windsurf hooks remain MCP-only here — the
hook shape is wired for claude-code + openclaw only.)

## Read-only enumeration reuse (the no-target `capability` audit, D-05-27)

`agents/enumerate.rs` (the no-target `capability` audit) **reads** these same config
shapes to enumerate what's already installed — it never writes. It reuses the
writer's key/format resolution so the read agrees with the write:

- MCP key shape: `writer::openclaw_key` (probed `mcpServers` ∨ `mcp.servers`),
  Copilot's `servers` (VS Code) vs `mcpServers` (CLI), and `writer::toml_to_json`
  for Codex `[mcp_servers.*]`. JSONC configs parse via `jsonc_parser`. Plugin
  `.mcp.json` reuses the same `scan_mcp_file` reader (key `mcpServers`).
- Skills: each `<skill_dir>/<name>/` containing `SKILL.md` (the root-relative
  `scan_skills_dir`, reused inside each plugin's `skills/`).
- Hooks (Claude Code + plugins): `~/.claude/settings.json` with a `hooks` key +
  `~/.claude/hooks/*.json` (the root-relative `scan_hooks_dir`, reused inside each
  plugin's `hooks/`).
- Rules (Cursor, v1): `~/.cursor/rules/*.mdc` + `.cursorrules`/`.windsurfrules`.
- **Slash commands + subagents (→ skill)**: Claude `commands/*.md` + `agents/*.md`,
  Codex `prompts/*.md`, and Gemini `commands/*.toml` (the `prompt` field) are each
  synthesized as a `SKILL.md` anchor (the backend has no `command`/`agent` kind;
  Claude treats commands + skills as one mechanism). A namespaced command
  (`commands/lde/x.md`) keeps its `lde:x` name via a `name:` frontmatter prepend
  when the source has none.
- **Plugin cache (Claude only)**: `~/.claude/plugins/cache/<mp>/<plugin>/<ver>/` —
  only the active version (per `installed_plugins.json`, else the
  lexically-greatest version dir) is read, and its `skills/` / `.mcp.json` /
  `hooks/` / `commands/` / `agents/` / `.claude-plugin/plugin.json` each become a
  capability mounted under `<agent>/plugins/<mp>__<plugin>/`. Lock/vendor/binary
  dirs (`.in_use`, `bin/`, `node_modules`, …) are excluded.

The writers expose **no read accessor**, so the JSON/TOML reads in
`enumerate.rs` are new read-only code; the synthetic bundle paths
(`<agent>/skills/<name>/…`, `<agent>/mcp/<server>/mcp.json`,
`<agent>/commands/<name>/SKILL.md`, `<agent>/plugins/<mp>__<plugin>/…`, …) match
the backend `discovery.py` anchor layout so one upload scans like a repo (the
backend fan-out further splits a bundled plugin tree into per-capability scans).
