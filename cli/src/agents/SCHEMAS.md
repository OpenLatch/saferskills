# Agent config schemas + live-verification checklist (D-05-15)

Pinned known-good config shapes the 8 writers target, with the official source +
retrieval date. The MEDIUM/LOW (volatile) surfaces carry a **live-verification
gate**: their checkbox stays ☐ until a maintainer installs the entry against a
real running agent and confirms it loads, then ticks it here. A surface that
cannot be verified ships **detect-only with a copy-paste fallback** for that one
surface — never a per-agent descope (the full-8 wedge is non-negotiable).

> This CLI ships exactly the **two install shapes** of D-05-16: `mcp_server`
> (format-preserving map-merge) and `skill` (folder copy). Surfaces outside those
> two (Windsurf *hooks*, Cline/Cursor *Rules*, Codex `openai.yaml`) are **not
> written** by this CLI, so they need no live-verify here — they are listed only
> to record why they're out of scope.

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

Out-of-scope surfaces (NOT written by this CLI — no live-verify needed here):
Windsurf hooks (`.windsurf/hooks.json`), Cline/Cursor Rules, Gemini skill dir,
Codex `openai.yaml`.

## Read-only enumeration reuse (`scan --local`, D-05-27)

`agents/enumerate.rs` (the `scan --local` audit) **reads** these same config
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
