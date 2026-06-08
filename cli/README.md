# saferskills

**Every AI capability, independently scanned.** Install Skills and MCP servers to any AI agent with a verified SaferSkills trust score checked at install time.

```bash
npx saferskills info mcp-server-github        # see an item's score + findings
npx saferskills install mcp-server-github     # install to your detected agents
npx saferskills scan ./my-skill        # scan a local capability
npx saferskills scan --local           # audit every capability installed across your agents (incl. commands, subagents & plugins)
```

No install required — `npx saferskills <command>` runs the prebuilt native binary. Or install it permanently:

```bash
npm install -g saferskills      # npm
cargo install saferskills       # crates.io
```

## What it does

SaferSkills scans Skills, MCP servers, hooks, and plugins for security, supply-chain, maintenance, transparency, and community signals — producing a public, methodology-backed trust score with a full rule trace. The CLI is a thin, fail-open client of the public API: reads are unauthenticated and uncapped, and the *safe path is the easy path*.

## Commands

| Command | Status | What it does |
|---|---|---|
| `info <name>` (alias `check`) | ✅ | Resolve a name → catalog item; print score, tier, findings, and the report URL. |
| `install <name>` | ✅ | Install a Skill / MCP server to your detected agents. Shows a **digest** (global score + 5-axis breakdown), discloses **which agents** it will write to, then gates on the **aggregate score**: below `min_score` (default 90) it warns + confirms; a red-tier (`< 40`) item requires typing the name. |
| `uninstall <name>` | ✅ | Reverse exactly what an install wrote. |
| `update [--all]` | ✅ | Refresh installed capabilities; re-verify scores. |
| `list` | ✅ | Show your **full local inventory** — every capability discovered across your detected agents (the same discovery `scan --local` performs), regardless of how it was installed — each annotated with its security score where known (CLI-installed → live current score + drift; previously scanned → cached score + age; otherwise `○ not scanned`). On a TTY it then offers to scan the unscanned ones inline and re-renders; `--json`/`--quiet`/`--non-interactive` print a `scan --local` hint instead. |
| `search [query]` (alias `find`) | ✅ | **Interactive catalog finder + installer.** On a TTY it opens an fzf-style terminal UI: type to live-filter a ranked list (debounced server search, kept visible while refreshing), narrow by **facets** (kind / agent / scan-tier / min-score) in a sidebar (`Ctrl-F` toggles focus), multi-select with `Tab`, preview each row's score breakdown + top findings, then `Enter` to install the marked set in one flow (auto-targets every compatible detected agent, through the same install score-gate). No query → the **trending** list. Hooks/plugins/rules are shown for discovery but **skipped on install** (the CLI installs Skills + MCP servers only) with a report link. Headless (`--json`, `--non-interactive`, or a non-TTY) emits the catalog envelope as JSON on stdout and never launches the UI; `--kind`/`--agent`/`--scan-tier`/`--score-min`/`--sort`/`--limit`/`--show-low-quality` filter either path. |
| `doctor` | ✅ | Diagnose registry-vs-filesystem drift. |
| `scan [path\|url]` | ✅ | Scan a local path or GitHub URL. With `--local` (or no target), **audit every capability installed across your detected agents** — skills, MCP servers, hooks, rules, **slash commands, subagents, and installed plugins** are discovered from each agent's own config (Claude `commands/`+`agents/`+`plugins/cache/`, Codex `prompts/`, Gemini `commands/`), bundled into one upload, scanned in one run, and rendered as a single per-capability audit report. Commands + subagents are scored as Skills; each plugin's active version is decomposed into its nested capabilities. `--private` keeps the run unlisted; `--detailed` expands per-capability axis bars + inline findings. |
| `completion <shell>` | ✅ | Print a shell completion script. |

## Global flags

`--json` (machine-readable output on stdout), `--no-color` / `--color <auto\|always\|never>`, `-v/--verbose`, `-q/--quiet`, `--yes`, `--force`, `--non-interactive` (alias `--no-input`).

Output discipline: **stdout is machine data** (JSON), **stderr is everything human** (steps, warnings, errors, the banner). Honors `NO_COLOR`, `CLICOLOR_FORCE`, and `TERM=dumb`. The two-line `SaferSkills` banner prints on every command: a full-width brand rule — sized to the exact terminal width and tinted a fresh, calm tone from a curated palette on each run — above a dimmed `v<version> · An OpenLatch project` line (suppressed under `--json`/`--quiet`, and for `completion`/`man`).

## Show your score — README badge

Every scanned capability has a **live trust badge** that re-renders on each re-scan. Embed it in your project's README so installers see the independent SaferSkills score before they run anything:

```markdown
[![SaferSkills 92/100](https://saferskills.ai/badge/<scan_id>/<score>.svg)](https://saferskills.ai/items/<slug>)
```

The badge links to the full [public report at `saferskills.ai/items/<slug>`](https://saferskills.ai) — score, four-tier breakdown, every rule that fired, and the vendor right-of-reply. Copy the exact snippet for your capability from its report page (the **⧉ Copy to MD** button on `saferskills.ai/items/<slug>`).

## Configuration

State lives under `~/.saferskills/` (override with `SAFERSKILLS_DIR`):

- `config.toml` — `api_url`, `min_score`, `telemetry`.
- `installs.json` — the install registry, used by `install` / `uninstall` / `update` and by `list` to show the live current score of a CLI-installed capability.
- `scan_cache.json` — the local scan-results cache. `scan --local` writes each scored capability here (keyed by a content hash of its files, drift-aware) so `list` can show a score for a capability that was previously scanned but never installed via the CLI. Entries older than 90 days are dropped. **`scan --local` does not read `installs.json`** — it audits whatever is installed across your agents' own config dirs (skills, MCP servers, hooks, rules, slash commands, subagents, and the active version of each installed plugin), regardless of how it got there, so you need no prior saferskills installs to audit your setup.

The API origin resolves as `SAFERSKILLS_API_URL` env → `config.toml` `api_url` → `https://saferskills.ai`.

The install score gate resolves as `SAFERSKILLS_MIN_SCORE` env → `config.toml` `min_score` → `90`. An item scoring below it (or unscored) warns and asks before installing; a red-tier (`< 40`) item requires typing the item name. `--yes` confirms a below-threshold install; only `--force` bypasses the red-tier type-name gate.

## Telemetry

Two anonymous, privacy-preserving channels — never arguments, names, paths, or any personal data:

- **Usage analytics** — which command ran, its exit code, a coarse duration. **Off by default and asked once**: the first interactive run prompts you and saves your answer to `~/.saferskills/config.toml`. Force on with `SAFERSKILLS_TELEMETRY=1`.
- **Install reporting** — an anonymous agent + capability-kind count when you install something, powering catalog popularity. Sent automatically; **no prompt**.

Both are silenced together by `SAFERSKILLS_NO_TELEMETRY=1` (`DO_NOT_TRACK` and `CI` are honored the same way), and non-interactive runs never prompt. See <https://saferskills.ai/privacy>.

Source and fork builds send **nothing** on either channel: telemetry requires a key baked in at release time, so any binary you build yourself is always inert.

## Building from source

```bash
cd cli
cargo build --release          # → target/release/saferskills
cargo test
cargo clippy --all-targets -- -D warnings
```

TLS is rustls-only (no OpenSSL). The binary is a single ~5 MB executable with sub-second start.

## Local development

Run any command straight from the workspace with `cargo run` — everything after `--` is passed to the CLI, exactly as if you'd typed `saferskills …`:

```bash
cd cli
cargo run -- info mcp-server-github          # → saferskills info mcp-server-github
cargo run -- --json info mcp-server-github   # global flags go after `--` too
cargo run -- scan ./my-skill
cargo run -- completion bash
```

A debug build is slower to start; for a release-speed binary use `cargo run --release -- <args>`.

### Pointing at a local API

Source builds send no telemetry (the analytics key is baked in only at release time), but they still hit the public API at `https://saferskills.ai` by default. To develop against a backend running locally, override the origin with `SAFERSKILLS_API_URL`:

**bash / zsh** — prefix the command (scopes the var to that one invocation):

```bash
SAFERSKILLS_API_URL=http://localhost:8000 cargo run -- info mcp-server-github

# or export it for the whole shell session:
export SAFERSKILLS_API_URL=http://localhost:8000
cargo run -- info mcp-server-github
```

**PowerShell** — set `$env:` first (PowerShell has no inline `VAR=val cmd` form):

```powershell
$env:SAFERSKILLS_API_URL = "http://localhost:8000"
cargo run -- info mcp-server-github

# clear it again when done:
Remove-Item Env:\SAFERSKILLS_API_URL
```

### Environment variables

| Variable | Effect |
|---|---|
| `SAFERSKILLS_API_URL` | API origin to call. Precedence: this env → `config.toml` `api_url` → `https://saferskills.ai`. |
| `SAFERSKILLS_MIN_SCORE` | Minimum aggregate score (0–100) that installs without a confirm. Precedence: this env → `config.toml` `min_score` → `90`. |
| `SAFERSKILLS_DIR` | Override the state dir (default `~/.saferskills/` — holds `config.toml` + `installs.json`). Handy for an isolated dev sandbox. |
| `SAFERSKILLS_NO_TELEMETRY` | Set to disable **all** telemetry (usage analytics + install reporting). `DO_NOT_TRACK` and `CI` are honored the same way. (Source builds are inert regardless.) |
| `SAFERSKILLS_TELEMETRY` | Force usage analytics on (`1`/`true`) or off (`0`), skipping the first-run prompt. Does not affect install reporting. |
| `NO_COLOR` / `CLICOLOR_FORCE` / `TERM=dumb` | Standard color controls; `--color <auto\|always\|never>` overrides them. |

Precedence across all config is **CLI flags → `SAFERSKILLS_*` env → `config.toml` → defaults**.

## Publishing

Published via [npm Trusted Publishers (OIDC)](https://docs.npmjs.com/trusted-publishers) and [crates.io Trusted Publishing](https://crates.io) — no long-lived registry tokens in CI. The release path is `.github/workflows/publish-npm.yml`: it builds 5 platform binaries, signs them (cosign keyless) with SBOMs, publishes the scoped `@openlatch/saferskills-<platform>` packages + the unscoped `saferskills` main package, and the `saferskills` crate.

---

An OpenLatch project · <https://saferskills.ai>
