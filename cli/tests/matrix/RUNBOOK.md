# Install matrix — manual real-agent sign-off (CLI-12, DoD)

The 24-scenario install matrix is **8 agents × 3 OSes**. It has two layers:

| Layer | What | Where | Gate |
|---|---|---|---|
| **Synthetic — agent dimension (8×)** | `install → uninstall` through the real binary against a mock API, with each agent's install surface faked under a throw-away `HOME`; asserts the MCP entry lands under the correct per-agent **key landmine** + reverses cleanly, and the `SKILL.md` folder-copy for skill-capable agents. | `cli/tests/matrix.rs` (`#![cfg(unix)]`) — runs in the `cli-test` CI lane (Linux). | **Automated, gating.** |
| **Synthetic — OS dimension (×3)** | Build + run the released binary on macOS / Linux / Windows. | `publish-npm.yml`: the 5-target build matrix (size-gated per OS) + the 3-OS `verify-publish` smoke (`saferskills --version` on ubuntu/macos/windows). | **Automated, on release** (the openlatch-client approach — cross-OS lives in the release matrix, not a per-PR lane). |
| **Manual real-agent (this runbook)** | `install` against a **real** install of each agent on each OS for the highest failure-risk cases. | This file. | **DoD sign-off ≥ 22/24.** |

`matrix.rs` covers the 8 agents deterministically on Linux (the writer logic that varies by OS is path-sep / newline / `%APPDATA%` / ACL); `dirs::home_dir()` honours `$HOME` only on unix, so the faked-`HOME` matrix is Linux-only and Windows/macOS coverage comes from the OS layer above + the cells below.

## How to run a cell

On a machine with the agent **actually installed**:

```bash
# 1. a clean MCP install to just this agent, then confirm + reverse it
npx saferskills install <a-real-mcp-item> --to <agent>
npx saferskills list                 # shows the row + current score
#   → open the agent, confirm the MCP server is live ("write succeeded" ≠ "active":
#     OpenClaw + Windsurf need a gateway/editor restart; re-check after restart)
npx saferskills uninstall <a-real-mcp-item>
npx saferskills doctor               # no registry-vs-filesystem drift

# 2. (skill-capable agents) repeat with a real skill item
npx saferskills install <a-real-skill-item> --to <agent>
npx saferskills uninstall <a-real-skill-item>
```

A cell **passes** when: the entry lands under the agent's documented key, the agent loads it, `uninstall` reverses it exactly, and `doctor` reports a clean state.

## Highest failure-risk cases (verify these first — design.md §4/§5)

- **Windsurf** — global-only MCP (`~/.codeium/windsurf/mcp_config.json`), remote key `serverUrl` (not `url`); hooks (`.windsurf/hooks.json`) are MED-confidence.
- **Cline** — resolve the actual VS Code variant dir (`Code` / `Code - Insiders` / `VSCodium`) for `…/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`; CLI fallback `~/.cline/mcp.json`.
- **OpenClaw** — ambiguous key shape (`mcpServers` vs nested `mcp.servers`); MED confidence. Confirm the writer respected the pre-existing shape.
- **Codex (Windows)** — TOML `[mcp_servers.<name>]`; Codex Desktop has been observed to rewrite/drop MCP entries on Windows restart — **re-verify after a restart**.

## 24-cell sign-off table

Record `✅` / `❌` (+ a note) per cell. DoD bar: **≥ 22/24** pass.

| Agent | macOS | Linux | Windows |
|---|---|---|---|
| claude-code | ☐ | ☐ | ☐ |
| cursor | ☐ | ☐ | ☐ |
| codex | ☐ | ☐ | ☐ (re-check after restart) |
| copilot | ☐ | ☐ | ☐ |
| windsurf | ☐ | ☐ | ☐ |
| cline | ☐ | ☐ | ☐ |
| gemini | ☐ | ☐ | ☐ |
| openclaw | ☐ | ☐ | ☐ |

**Result: __ / 24** — signed-off by ______ on ________.

> Failures feed `cli/src/agents/SCHEMAS.md` (per-writer confidence) + a copy-paste fallback note for I-06. A MED/LOW writer's confidence is only raised after a recorded pass here.
